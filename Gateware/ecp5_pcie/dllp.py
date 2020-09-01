from nmigen import *
from nmigen.build import *
from nmigen.lib.fifo import SyncFIFOBuffered

from enum import IntEnum
from .layouts import dllp_layout
from .serdes import K, D, Ctrl, PCIeScrambler
from .crc import CRC

# Page 137 in PCIe 1.1
class Type(IntEnum):
    Ack         = 0,
    Nak         = 1,
    PM          = 2,
    InitFC1_P   = 4,
    InitFC1_NP  = 5,
    InitFC1_Cpl = 6,
    InitFC2_P   = 12,
    InitFC2_NP  = 13,
    InitFC2_Cpl = 14,
    UpdateFC_P  = 8,
    UpdateFC_NP = 9,
    UpdateFC_Cpl= 10,

class PCIeDLLPTransmitter(Elaboratable):
    """
    PCIe Data Link Layer Packet transmitter
    """
    def __init__(self, lane : PCIeScrambler):
        self.dllp   = Record(dllp_layout)
        self.__lane = lane

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        dllp = self.dllp

        # TODO: Maybe rethink CRC implementation to make this unnecessary.
        symbols = [Signal(9), Signal(9)]
        out_symbols = [Signal(9), Signal(9)]
        last_symbol = Signal(9)

        m.d.rx += last_symbol.eq(out_symbols[1])
        m.d.rx += self.__lane.tx_symbol.eq(Cat(last_symbol, out_symbols[0]))

        # Delay 1 clock cycle for CRC calculation
        m.d.rx += out_symbols[0].eq(symbols[0])
        m.d.rx += out_symbols[1].eq(symbols[1])

        # Set up CRC (PCIe 1.1 page 167)
        m.submodules.crc = crc = DomainRenamer("rx")(CRC(Cat(symbols[0][0:8], symbols[1][0:8]), 0xFFFF, 0x100B, 16))

        # See figure 3-11.
        crc_out = ~Cat(crc.output[::-1])
        m.d.rx += crc.reset.eq(0)

        # TODO: Do it properly instead of guessing around.
        # It does work but it is very hacky
        with m.FSM(domain="rx"):
            with m.State("Idle"):
                m.d.rx += crc.reset.eq(0)
                with m.If(dllp.valid):
                    m.d.rx += symbols[0].eq(Cat(dllp.type_meta, Const(0, 1), dllp.type))
                    m.d.rx += symbols[1].eq(dllp.header[2:8])
                    m.next = "tx-1"
                #with m.Else():
                m.d.rx += out_symbols[0].eq(0)
                m.d.rx += last_symbol.eq(0)
            with m.State("tx-1"):
                m.d.rx += symbols[0].eq(Cat(dllp.data[8:12], Const(0, 2), dllp.header[0:2]))
                m.d.rx += symbols[1].eq(dllp.data[0:8])
                m.d.rx += last_symbol.eq(Ctrl.SDP)
                m.next = "tx-2"
            with m.State("tx-2"):
                m.next = "tx-3"
            with m.State("tx-3"):
                m.d.rx += out_symbols[0].eq(crc_out[0:8])
                m.d.rx += out_symbols[1].eq(crc_out[8:16])
                m.d.rx += crc.reset.eq(1)
                m.next = "tx-4"
            with m.State("tx-4"):
                m.d.rx += out_symbols[0].eq(Ctrl.END)
                with m.If(dllp.valid):
                    m.d.rx += symbols[0].eq(Cat(dllp.type_meta, Const(0, 1), dllp.type))
                    m.d.rx += symbols[1].eq(dllp.header[2:8])
                    m.d.rx += crc.reset.eq(0)
                    m.next = "tx-1"
                with m.Else():
                    m.d.rx += crc.reset.eq(1)
                    m.next = "Idle"

        return m

class PCIeDLLPReceiver(Elaboratable):
    """
    PCIe Data Link Layer Packet receiver
    """
    def __init__(self, lane : PCIeScrambler, fifo_depth = 8):
        self.dllp   = Record(dllp_layout)
        self.fifo   = DomainRenamer("rx")(SyncFIFOBuffered(width=len(self.dllp), depth=fifo_depth))
        self.__lane = lane

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        new_symbols = Signal(18)
        m.d.rx += new_symbols.eq(self.__lane.rx_symbol)
        symbols = [new_symbols[0:9], new_symbols[9:18]]

        # Align such that symbols are [0 1] [2 3] [4 5]
        last_symbol = Signal(9)
        m.d.rx += last_symbol.eq(symbols[1])
        aligned_symbols = Cat(last_symbol[0:8], symbols[0][0:8])

        # Set up CRC (PCIe 1.1 page 167)
        m.submodules.crc = crc = DomainRenamer("rx")(CRC(aligned_symbols, 0xFFFF, 0x100B, 16))
        m.submodules.fifo = self.fifo

        # See figure 3-11.
        crc_out = ~Cat(crc.output[::-1])

        m.d.rx += crc.reset.eq(self.__lane.rx_symbol[0:9] == Ctrl.SDP)
        m.d.comb += self.fifo.w_data.eq(self.dllp)

        with m.FSM(domain="rx"):
            with m.State("Idle"):
                m.d.rx += self.fifo.w_en.eq(0)
                m.d.rx += self.dllp.eq(0)
                with m.If(symbols[0] == Ctrl.SDP):
                    m.d.rx += self.dllp.type.eq(symbols[1][4:8])
                    m.d.rx += self.dllp.type_meta.eq(symbols[1][0:3])
                    m.next = "rx-1"
            with m.State("rx-1"):
                m.d.rx += self.dllp.header.eq(Cat(symbols[1][6:8], symbols[0][0:6]))
                m.d.rx += Cat(self.dllp.data[8:12]).eq(symbols[1][0:4])
                m.next = "rx-2"
            with m.State("rx-2"):
                m.d.rx += Cat(self.dllp.data[0:8]).eq(symbols[0][0:8])
                m.next = "rx-3"
            with m.State("rx-3"):
                # CRC input is just the lane data
                m.d.rx += self.dllp.valid.eq((symbols[1] == Ctrl.END) & (crc_out == crc.input))
                m.d.rx += self.fifo.w_en.eq(1)
                m.next = "Idle"

        return m