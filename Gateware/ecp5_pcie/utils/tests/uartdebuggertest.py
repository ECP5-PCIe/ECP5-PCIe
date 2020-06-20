import itertools

from nmigen import *
from nmigen.build import *
from nmigen_boards import versa_ecp5_5g as FPGA
from nmigen_stdio import serial
from ..utils import UARTDebugger, Resizer
from ..parts import PLL1Ch

__all__ = ["UARTDebuggerTest"]

class UARTDebuggerTest(Elaboratable):
    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        
        uart_pins = platform.request("uart", 0)
        m.domains.slow = ClockDomain()
        uart = serial.AsyncSerial(divisor = int(100 * 1000 * 1000 / 115200), pins = uart_pins)
        pllslow = PLL1Ch(ClockSignal("sync"), Signal(), Signal(), CLKI_DIV=2, CLKFB_DIV=1, CLK_DIV=12) # 100 -> 600 -> 50 MHz
        m.submodules += [uart, pllslow]

        m.d.comb += ClockSignal("slow").eq(pllslow.clkout)

        words = 4
        data = Signal(words * 8)
        m.d.slow += data.eq(data + 1)
        debugger = UARTDebugger(uart, words, 100, data, "slow", data[5])

        m.submodules += debugger
        return m

import os
os.environ["NMIGEN_verbose"] = "Yes"
FPGA.VersaECP55GPlatform().build(UARTDebuggerTest(), do_program=True, nextpnr_opts="--timing-allow-fail -r")