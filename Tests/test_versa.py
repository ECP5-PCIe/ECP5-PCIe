from amaranth import *
from amaranth.build import *
from amaranth.lib.cdc import FFSynchronizer
from amaranth_boards import versa_ecp5_5g as FPGA
from amaranth_stdio.serial import AsyncSerial

class VersaTest(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        
        platform.add_resources([Resource("test", 0, Pins("B19", dir="o"))]) # X3 4
        m.d.comb += platform.request("test", 0).o.eq(ClockSignal("sync"))
        platform.add_resources([Resource("test", 1, Pins("A18", dir="o"))]) # X4 39
        m.d.comb += platform.request("test", 1).o.eq(ClockSignal("sync"))

        leds = Cat(platform.request("led", i) for i in range(8))
        leds_alnum = Cat(platform.request("alnum_led", 0))

        led_sig = Signal(8, reset=1)
        m.d.comb += leds.eq(0x3)

        toggle = Signal()

        cdiv = Signal(range(int(500e6)))
        m.d.sync += cdiv.eq(cdiv + 1)

        with m.If(cdiv >= int(100e6)):
            m.d.sync += led_sig.eq(led_sig.rotate_left(1))
            m.d.sync += cdiv.eq(0)
            m.d.sync += toggle.eq(~toggle)

        
        cnt = Signal(32)

        m.d.sync += cnt.eq(cnt + 1)

        m.d.comb += leds_alnum.eq(Mux(cnt[27], 0xFFFF, 0x0000))

        return m

# -------------------------------------------------------------------------------------------------

import sys
import serial
from glob import glob


import os
os.environ["AMARANTH_verbose"] = "Yes"


if __name__ == "__main__":
    FPGA.VersaECP55GPlatform().build(VersaTest(), do_program=True, nextpnr_opts="-r")