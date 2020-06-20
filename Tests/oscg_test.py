import pcie_adapter as FPGA
from avr_test import Test as AVRTest
from nmigen import *
from nmigen.build import *
from ecp5_pcie.utils.parts import PLL1Ch

class Test(Elaboratable):
    def elaborate(self, platform):
        m = Module()

        debug_sma = platform.request("debug_sma").o
        out1Hz = platform.request("led", 1).o
        #serdes_clk = platform.request("serdes_clk", 1).i

        clock = Signal()
        
        oscg = Instance("OSCG",
            o_OSC=clock,
            p_DIV="2", # 2.4 MHz
        )
        m.submodules += oscg

        dom = ClockDomain()
        m.d.comb += dom.clk.eq(clock)
        m.domains += dom

        counter = Signal(reset=155 * 1000 * 500, shape=range(155 * 1000 * 500))

        m.d.comb += debug_sma.eq(counter[6])

        with m.If(counter == 0):
            m.d.dom += [counter.eq(counter.reset), out1Hz.eq(~out1Hz)]
        with m.Else():
            m.d.dom += counter.eq(counter - 1)
        
        return m

import os
os.environ["NMIGEN_verbose"] = "Yes"

if __name__ == "__main__":
    FPGA.ECP5PCIeAdapterPlatform().build(Test(), do_program=True)