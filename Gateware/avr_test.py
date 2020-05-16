import pcie_adapter as FPGA
from nmigen import *
from nmigen.build import *
from utils.parts import PLL1Ch

class Test(Elaboratable):
    def __init__(self, debugout = True):
        self.debugout = debugout

    def elaborate(self, platform):
        m = Module()

        avr_uart = platform.request("avr_uart")
        usb_uart = platform.request("usb_uart")
        avr_clk = platform.request("avr_clk").o
        avr_rst = platform.request("avr_rst").o # For programming with ISP programmer, comment this line out and insert 'avr_rst = Signal()' instead
        debug_sma = Signal()
        if(self.debugout):
            debug_sma = platform.request("debug_sma").o
        pll_lock = platform.request("led", 0).o
        button = platform.request("button", 0).i

        clk16M = Signal()

        pll = PLL1Ch(ClockSignal("sync"), clk16M, pll_lock, CLKI_DIV=3, CLKFB_DIV=4, CLK_DIV=10) # 12 -> 160 -> 16 MHz
        
        m.d.comb += avr_uart.tx.o.eq(usb_uart.rx.i)
        m.d.comb += usb_uart.tx.o.eq(avr_uart.rx.i)
        m.d.comb += debug_sma.eq(clk16M)
        m.d.comb += avr_clk.eq(clk16M)
        m.d.comb += avr_rst.eq(~button)

        m.submodules += pll
        return m

if __name__ == "__main__":
    FPGA.PCIeAdapterPlatform().build(Test(), do_program=True)