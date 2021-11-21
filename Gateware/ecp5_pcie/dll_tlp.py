from nmigen import *
from nmigen.build import *
from nmigen.lib.fifo import SyncFIFOBuffered

from enum import IntEnum
from .layouts import dllp_layout
from .serdes import K, D, Ctrl
from .crc import LCRC
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
        self.tlp_seq_num = Signal(12, reset=0x123) # TLP sequence number

        #self.tlp_data = Signal(4 * 8)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        ratio = self.ratio
        assert ratio == 4
        
        reset_crc = Signal(reset = 1)
        # TODO Warning: Endianness
        crc_input = Signal(32)
        m.submodules.lcrc = lcrc = LCRC(crc_input, reset_crc)

        last_valid = Signal()
        m.d.rx += last_valid.eq(self.tlp_sink.all_valid)
        last_last_valid = Signal() # TODO: Maybe there is a better way
        m.d.rx += last_last_valid.eq(last_valid)
        last_last_last_valid = Signal() # TODO: Maybe there is a better way 😿
        m.d.rx += last_last_last_valid.eq(last_last_valid)


        tlp_bytes = Signal(8 * self.ratio)
        tlp_bytes_before = Signal(8 * self.ratio)

        with m.If(self.tlp_sink.all_valid):
            m.d.comb += Cat(tlp_bytes[0 : 8 * ratio]).eq(Cat(self.tlp_sink.symbol)) # TODO: Endianness correct?
            m.d.rx += Cat(tlp_bytes_before[0 : 8 * ratio]).eq(Cat(self.tlp_sink.symbol)) # TODO: Endianness correct?
        with m.Else():
            m.d.comb += Cat(tlp_bytes[0 : 8 * ratio]).eq(lcrc.output) # TODO: Endianness correct?
            m.d.rx += Cat(tlp_bytes_before[0 : 8 * ratio]).eq(lcrc.output) # TODO: Endianness correct?

        #m.d.rx += Cat(tlp_bytes[8 * ratio : 2 * 8 * ratio]).eq(Cat(tlp_bytes[0 : 8 * ratio]))

        even_more_delay = [Signal(9) for i in range(4)]


        m.d.comb += self.tlp_sink.ready.eq(0) # TODO: maybe move to rx?

        delayed_symbol = Signal(32)
        m.d.rx += delayed_symbol.eq(Cat(self.tlp_sink.symbol))
        m.d.comb += crc_input.eq(delayed_symbol)

        for i in range(4):
            m.d.rx += self.dllp_source.valid[i].eq(0)

        for i in range(4):
            m.d.rx += self.dllp_source.valid[i].eq(0)

        with m.If(self.dllp_source.ready):
            m.d.comb += self.tlp_sink.ready.eq(1) # TODO: maybe move to rx?

            with m.If(~last_valid & self.tlp_sink.all_valid):
                m.d.comb += reset_crc.eq(0)
                m.d.comb += crc_input.eq(Cat(self.tlp_seq_num[8 : 12], Const(0, shape = 4), self.tlp_seq_num[0 : 8]))
                m.d.rx += even_more_delay[0].eq(Ctrl.STP)
                m.d.rx += even_more_delay[1].eq(self.tlp_seq_num[8 : 12])
                m.d.rx += even_more_delay[2].eq(self.tlp_seq_num[0 : 8])
                m.d.rx += even_more_delay[3].eq(tlp_bytes[8 * 0 : 8 * 1])
                #for i in range(4):
                #    m.d.rx += self.dllp_source.symbol[i].eq(even_more_delay[i])

            with m.Elif(last_valid & self.tlp_sink.all_valid):
                m.d.comb += reset_crc.eq(0)
                m.d.rx += even_more_delay[0].eq(tlp_bytes_before[8 * 1 : 8 * 2])
                m.d.rx += even_more_delay[1].eq(tlp_bytes_before[8 * 2 : 8 * 3])
                m.d.rx += even_more_delay[2].eq(tlp_bytes_before[8 * 3 : 8 * 4])
                m.d.rx += even_more_delay[3].eq(tlp_bytes[8 * 0 : 8 * 1])
                for i in range(4):
                    m.d.rx += self.dllp_source.symbol[i].eq(even_more_delay[i])
                for i in range(4):
                    m.d.rx += self.dllp_source.valid[i].eq(1)

            with m.Elif(last_valid & ~self.tlp_sink.all_valid): # Maybe this can be done better and replaced by the two if blocks above
                m.d.comb += reset_crc.eq(0)
                m.d.comb += self.tlp_sink.ready.eq(0) # TODO: maybe move to rx?
                m.d.rx += even_more_delay[0].eq(tlp_bytes_before[8 * 1 : 8 * 2])
                m.d.rx += even_more_delay[1].eq(tlp_bytes_before[8 * 2 : 8 * 3])
                m.d.rx += even_more_delay[2].eq(tlp_bytes_before[8 * 3 : 8 * 4])
                for i in range(4):
                    m.d.rx += self.dllp_source.symbol[i].eq(even_more_delay[i])
                for i in range(4):
                    m.d.rx += self.dllp_source.valid[i].eq(1)

            with m.Elif(last_last_valid & ~self.tlp_sink.all_valid):
                m.d.rx += self.dllp_source.symbol[3].eq(tlp_bytes[8 * 0 : 8 * 1])
                for i in range(3):
                    m.d.rx += self.dllp_source.symbol[i].eq(even_more_delay[i])
                for i in range(4):
                    m.d.rx += self.dllp_source.valid[i].eq(1)

            with m.Elif(last_last_last_valid & ~self.tlp_sink.all_valid):
                m.d.comb += self.tlp_sink.ready.eq(0) # TODO: maybe move to rx?
                m.d.rx += self.dllp_source.symbol[0].eq(tlp_bytes_before[8 * 1 : 8 * 2])
                m.d.rx += self.dllp_source.symbol[1].eq(tlp_bytes_before[8 * 2 : 8 * 3])
                m.d.rx += self.dllp_source.symbol[2].eq(tlp_bytes_before[8 * 3 : 8 * 4])
                m.d.rx += self.dllp_source.symbol[3].eq(Ctrl.END)
                for i in range(4):
                    m.d.rx += self.dllp_source.valid[i].eq(1)


        return m