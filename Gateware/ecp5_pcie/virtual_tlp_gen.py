from nmigen import *
from nmigen.build import *
from nmigen.lib.fifo import SyncFIFOBuffered

from enum import IntEnum
from .layouts import dllp_layout
from .serdes import K, D, Ctrl
from .crc import CRC
from .stream import StreamInterface

class PCIeVirtualTLPGenerator(Elaboratable):
    def __init__(self, ratio = 4):
        self.tlp_source = StreamInterface(8, ratio, name="TLP_Gen_Out")
        self.ratio = ratio

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        ratio = self.ratio

        timer = Signal(9)
        m.d.rx += timer.eq(timer + 1)

        with m.If(self.tlp_source.ready):
            with m.If(timer < 256):
                for i in range(ratio):
                    m.d.rx += self.tlp_source.symbol[i].eq(timer * ratio + i)
                    m.d.rx += self.tlp_source.valid[i].eq(1)

            with m.Else():
                for i in range(ratio):
                    m.d.rx += self.tlp_source.valid[i].eq(0)



        return m