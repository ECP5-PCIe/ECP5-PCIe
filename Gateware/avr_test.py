import pcie_adapter as FPGA
from nmigen import *
from nmigen.build import *

class Test(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        avr_uart = platform.request("avr_uart")
        usb_uart = platform.request("usb_uart")
        m.d.comb += avr_uart.tx.o.eq(usb_uart.rx.i)
        m.d.comb += usb_uart.tx.o.eq(avr_uart.rx.i)
        return m

FPGA.PCIeAdapterPlatform().build(Test(), do_program=True)