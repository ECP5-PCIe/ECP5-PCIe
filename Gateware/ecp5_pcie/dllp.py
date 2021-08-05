from nmigen import *
from nmigen.build import *
from nmigen.lib.fifo import SyncFIFOBuffered

from enum import IntEnum
from .layouts import dllp_layout
from .serdes import K, D, Ctrl, PCIeScrambler
from .crc import SingleCRC
from .stream import StreamInterface

# Page 137 in PCIe 1.1
class DLLPType(IntEnum):
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
    PCIe Data Link Layer Packet transmitter for x4 width

    Parameters
    ----------
    out_symbols : Signal(18)
        Symbols to TX Phy
    send : Signal()
        True when sending DLLPs
    """
    def __init__(self, ratio = 4):
        self.dllp = Record(dllp_layout)
        self.phy_source = StreamInterface(9, ratio)
        self.send = Signal()
        self.started_sending = Signal()
        self.enable = Signal(reset = 1)
        assert len(self.phy_source.symbol) == 4
        self.ratio = len(self.phy_source.symbol)

        self.dllp_data = Signal(4 * 8)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        dllp = self.dllp

        # The first 4 bytes
        dllp_data = self.dllp_data# = Signal(4 * 8)
        with m.If(dllp.valid):
        # Damn big endian
            m.d.comb += dllp_data.eq(Cat(
                dllp.type_meta, Const(0, 1), dllp.type,
                dllp.header[2:8], Const(0, 2),
                dllp.data[8:12], Const(0, 2), dllp.header[0:2],
                dllp.data[0:8],
                ))
            
        m.submodules.crc = crc = SingleCRC(dllp_data, 0xFFFF, 0x100B, 16)

        dllp_bytes = Cat(dllp_data, ~Cat(crc.output[::-1]))

        # First or second half of DLLP
        which_half = Signal()

        with m.If(dllp.valid & (self.send | which_half)):
            for i in range(4):
                m.d.comb += self.phy_source.valid[i].eq(1)

            with m.If(~which_half):
                m.d.rx += which_half.eq(1)
                m.d.comb += self.phy_source.symbol[0].eq(Ctrl.SDP)
                m.d.comb += self.started_sending.eq(1)

                for i in range(self.ratio - 1):
                    m.d.comb += self.phy_source.symbol[i + 1].eq(dllp_bytes[8 * i : 8 * i + 8])

            with m.Else():
                m.d.rx += which_half.eq(0)
                m.d.comb += self.started_sending.eq(0)
                for i in range(self.ratio - 1):
                    m.d.comb += self.phy_source.symbol[i].eq(dllp_bytes[8 * i + (self.ratio - 1) * 8 : 8 * i + 8 + (self.ratio - 1) * 8])

                m.d.comb += self.phy_source.symbol[3].eq(Ctrl.END)

        with m.Else():
            m.d.rx += which_half.eq(0)
            m.d.comb += self.started_sending.eq(0)
            for i in range(4):
                m.d.comb += self.phy_source.valid[i].eq(0)

        return m

class PCIeDLLPReceiver(Elaboratable):
    """
    PCIe Data Link Layer Packet receiver
    """
    def __init__(self, phy_sink : StreamInterface):
        self.dllp = Record(dllp_layout)
        self.phy_sink = phy_sink
        assert len(self.phy_sink.symbol) == 4
        self.ratio = len(self.phy_sink.symbol)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        dllp = self.dllp

        dllp_bytes = Signal(6 * 8)

        valid = Signal()

        m.submodules.crc = crc = SingleCRC(dllp_bytes[:4 * 8], 0xFFFF, 0x100B, 16)

        with m.If(self.phy_sink.symbol[0] == Ctrl.SDP):
            for i in range(self.ratio - 1):
                m.d.rx += Cat(dllp_bytes[8 * i : 8 * i + 8]).eq(self.phy_sink.symbol[i + 1])
            m.d.rx += valid.eq(0)

        with m.Elif(self.phy_sink.symbol[3] == Ctrl.END):
            for i in range(self.ratio - 1):
                m.d.rx += Cat(dllp_bytes[8 * i + (self.ratio - 1) * 8: 8 * i + 8 + (self.ratio - 1) * 8]).eq(self.phy_sink.symbol[i])
        
        m.d.rx += valid.eq(~Cat(crc.output[::-1]) == dllp_bytes[8 * 4:])

        with m.If(valid):
            m.d.rx += dllp.valid.eq(1)
            m.d.rx += dllp.type.eq(dllp_bytes[4:8])
            m.d.rx += dllp.type_meta.eq(dllp_bytes[0:3])
            m.d.rx += dllp.header.eq(Cat(dllp_bytes[8:14], dllp_bytes[22:24]))
            m.d.rx += dllp.data.eq(Cat(dllp_bytes[16:21], dllp_bytes[24:32]))

        return m