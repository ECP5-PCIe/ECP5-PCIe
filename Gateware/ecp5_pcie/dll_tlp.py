from nmigen import *
from nmigen.build import *
from nmigen.lib.fifo import SyncFIFOBuffered

from enum import IntEnum
from .layouts import dllp_layout
from .serdes import K, D, Ctrl
from .crc import CRC
from .stream import StreamInterface

class PCIeDLLTLPTransmitter(Elaboratable):
    """
    """
    def __init__(self, ratio = 4):
        self.tlp_sink = StreamInterface(8, ratio, name="TLP_Sink")
        self.dllp_source = StreamInterface(9, ratio, name="DLLP_Source")
        self.send = Signal()
        self.started_sending = Signal()
        assert len(self.dllp_source.symbol) == 4
        assert len(self.tlp_sink.symbol) == 4
        self.ratio = len(self.dllp_source.symbol)
        self.tlp_seq_num = Signal(12) # TLP sequence number

        #self.tlp_data = Signal(4 * 8)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        ratio = self.ratio
        assert ratio == 4
        
        reset_crc = Signal()
        # TODO Warning: Endianness
        m.submodules.crc = crc = CRC(Cat(self.tlp_sink.symbol), 0xFFFFFFFF, 0x04C11DB7, 32, reset_crc)

        last_valid = Signal()
        m.d.rx += last_valid.eq(self.tlp_sink.all_valid)
        last_last_valid = Signal() # TODO: Maybe there is a better way
        m.d.rx += last_last_valid.eq(last_valid)


        tlp_bytes = Signal(8 * self.ratio)
        tlp_bytes_before = Signal(8 * self.ratio)

        with m.If(self.tlp_sink.all_valid):
            m.d.comb += Cat(tlp_bytes[0 : 8 * ratio]).eq(Cat(self.tlp_sink.symbol)) # TODO: Endianness correct?
            m.d.rx += Cat(tlp_bytes_before[0 : 8 * ratio]).eq(Cat(self.tlp_sink.symbol)) # TODO: Endianness correct?
        with m.Else():
            m.d.comb += Cat(tlp_bytes[0 : 8 * ratio]).eq(crc.output[::-1]) # TODO: Endianness correct?
            m.d.rx += Cat(tlp_bytes_before[0 : 8 * ratio]).eq(crc.output[::-1]) # TODO: Endianness correct?

        #m.d.rx += Cat(tlp_bytes[8 * ratio : 2 * 8 * ratio]).eq(Cat(tlp_bytes[0 : 8 * ratio]))


        m.d.comb += self.tlp_sink.ready.eq(0) # TODO: maybe move to rx?

        for i in range(4):
            m.d.rx += self.dllp_source.valid[i].eq(0)

        with m.If(self.dllp_source.ready):
            m.d.comb += self.tlp_sink.ready.eq(1) # TODO: maybe move to rx?
            for i in range(4):
                m.d.rx += self.dllp_source.valid[i].eq(1)

            with m.If(~last_valid & self.tlp_sink.all_valid):
                m.d.rx += self.dllp_source.symbol[0].eq(Ctrl.STP)
                m.d.rx += self.dllp_source.symbol[1].eq(self.tlp_seq_num[8 : 12])
                m.d.rx += self.dllp_source.symbol[2].eq(self.tlp_seq_num[0 : 8])
                m.d.rx += self.dllp_source.symbol[3].eq(tlp_bytes[8 * 0 : 8 * 1])

            with m.Elif(last_valid & self.tlp_sink.all_valid):
                m.d.rx += self.dllp_source.symbol[0].eq(tlp_bytes_before[8 * 1 : 8 * 2])
                m.d.rx += self.dllp_source.symbol[1].eq(tlp_bytes_before[8 * 2 : 8 * 3])
                m.d.rx += self.dllp_source.symbol[2].eq(tlp_bytes_before[8 * 3 : 8 * 4])
                m.d.rx += self.dllp_source.symbol[3].eq(tlp_bytes[8 * 0 : 8 * 1])

            with m.Elif(last_valid & ~self.tlp_sink.all_valid): # Maybe this can be done better and replaced by the two if blocks above
                m.d.comb += self.tlp_sink.ready.eq(0) # TODO: maybe move to rx?
                m.d.rx += self.dllp_source.symbol[0].eq(tlp_bytes_before[8 * 1 : 8 * 2])
                m.d.rx += self.dllp_source.symbol[1].eq(tlp_bytes_before[8 * 2 : 8 * 3])
                m.d.rx += self.dllp_source.symbol[2].eq(tlp_bytes_before[8 * 3 : 8 * 4])
                m.d.rx += self.dllp_source.symbol[3].eq(tlp_bytes[8 * 0 : 8 * 1])

            with m.Elif(last_last_valid & ~self.tlp_sink.all_valid):
                m.d.comb += self.tlp_sink.ready.eq(0) # TODO: maybe move to rx?
                m.d.rx += self.dllp_source.symbol[0].eq(tlp_bytes_before[8 * 1 : 8 * 2])
                m.d.rx += self.dllp_source.symbol[1].eq(tlp_bytes_before[8 * 2 : 8 * 3])
                m.d.rx += self.dllp_source.symbol[2].eq(tlp_bytes_before[8 * 3 : 8 * 4])
                m.d.rx += self.dllp_source.symbol[3].eq(Ctrl.END)

        return m