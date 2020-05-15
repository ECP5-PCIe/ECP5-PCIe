import pcie_adapter as FPGA
from avr_test import Test as AVRTest
from nmigen import *
from nmigen.build import *
from utils.parts import PLL1Ch

class Test(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        debug_sma = platform.request("debug_sma").o
        pll_lock = platform.request("led", 1).o
        to_pll = platform.request("to_pll", 0).o
        from_pll = platform.request("from_pll", 0).i

        pll = PLL1Ch(ClockSignal("sync"), to_pll, pll_lock, CLKI_DIV=3, CLKFB_DIV=4, CLK_DIV=10) # 12 -> 160 -> 16 MHz
        avr_test = AVRTest(debugout=False)

        m.d.comb += debug_sma.eq(from_pll)

        m.submodules += avr_test
        m.submodules += pll
        return m

if __name__ == "__main__":
    FPGA.PCIeAdapterPlatform().build(Test(), do_program=True)