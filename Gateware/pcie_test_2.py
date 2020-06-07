from nmigen import *
from nmigen.build import *
from nmigen_boards import versa_ecp5_5g as FPGA
from nmigen.lib.cdc import FFSynchronizer as MultiReg
from nmigen_stdio.serial import AsyncSerial
from utils.utils import UARTDebugger
from ecp5_serdes import LatticeECP5PCIeSERDES
from serdes import K, D

# Usage: python pcie_test_2.py run
#        python pcie_test_2.py grab

CAPTURE_DEPTH = 8192

class SERDESTestbench(Elaboratable):
    def elaborate(self, platform):
        m = Module()

        m.submodules.serdes = serdes = LatticeECP5PCIeSERDES()
        m.d.comb += [
            #serdes.txd.eq(K(28,3)),
            serdes.txk.eq(1),
            serdes.rxdet.eq(1),
            serdes.rxinv.eq(0),
        ]

        #m.domains.sync = ClockDomain()
        m.domains.rx = ClockDomain()
        m.domains.tx = ClockDomain()
        m.d.comb += [
            #ClockSignal("sync").eq(serdes.refclk),
            ClockSignal("rx").eq(serdes.rxclk),
            ClockSignal("tx").eq(serdes.txclk),
        ]

        m.d.tx += serdes.txd.eq(serdes.txd + 1)
        #with m.FSM(domain="tx"):
        #    with m.State("1"):
        #        m.d.tx += serdes.txd.eq(K(28,5))
        #        m.next = "2"
        #    with m.State("2"):
        #        m.d.tx += serdes.txd.eq(K(28,1))
        #        m.next = "3"
        #    with m.State("3"):
        #        m.d.tx += serdes.txd.eq(K(28,1))
        #        m.next = "4"
        #    with m.State("4"):
        #        m.d.tx += serdes.txd.eq(K(28,1))
        #        m.next = "1"

        platform.add_resources([Resource("test", 0, Pins("B19", dir="o"))]) # Arduino tx
        m.d.comb += platform.request("test").o.eq(ClockSignal("sync"))

        #platform.add_platform_command("""FREQUENCY NET "ref_clk" 100 MHz;""")
        #platform.add_platform_command("""FREQUENCY NET "rx_clk" 250 MHz;""")
        #platform.add_platform_command("""FREQUENCY NET "tx_clk" 250 MHz;""")

        refclkcounter = Signal(32)
        m.d.sync += refclkcounter.eq(refclkcounter + 1)
        rxclkcounter = Signal(32)
        m.d.rx += rxclkcounter.eq(rxclkcounter + 1)
        txclkcounter = Signal(32)
        m.d.tx += txclkcounter.eq(txclkcounter + 1)

        led_att1 = platform.request("led",0)
        led_att2 = platform.request("led",1)
        led_sta1 = platform.request("led",2)
        led_sta2 = platform.request("led",3)
        led_err1 = platform.request("led",4)
        led_err2 = platform.request("led",5)
        led_err3 = platform.request("led",6)
        led_err4 = platform.request("led",7)
        m.d.comb += [
            led_att1.eq(~(refclkcounter[25])),
            led_att2.eq(~(serdes.rlsm)),
            led_sta1.eq(~(rxclkcounter[25])),
            led_sta2.eq(~(txclkcounter[25])),
            led_err1.eq(~(serdes.rlos)),
            led_err2.eq(~(serdes.rlol | serdes.tlol)),
            led_err3.eq(~(0)),#serdes.rxde0)),
            led_err4.eq(~(0)),#serdes.rxce0)),
        ]

        m.domains.por = ClockDomain(reset_less=True)
        reset_delay = Signal(range(2047), reset=2047)
        m.d.comb += [
            ClockSignal("por").eq(ClockSignal("sync")),
            #ResetSignal("sync").eq(reset_delay != 0)
        ]
        with m.If(reset_delay != 0):
            m.d.por += reset_delay.eq(reset_delay - 1)

        trigger_rx  = Signal()
        trigger_ref = Signal()
        m.submodules += MultiReg(trigger_ref, trigger_rx, o_domain="rx")

        uart_pins = platform.request("uart", 0)
        uart = AsyncSerial(divisor = int(100), pins = uart_pins)
        m.submodules += uart
        debug = UARTDebugger(uart, 2, CAPTURE_DEPTH, Cat(serdes.rxd, serdes.rxk, serdes.rlsm, Signal(6)), "rx") # serdes.lane.rx_present & serdes.lane.rx_locked)
        m.submodules += debug

        return m

# -------------------------------------------------------------------------------------------------

import sys
import serial


import os
os.environ["NMIGEN_verbose"] = "Yes"


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        if arg == "run":
            FPGA.VersaECP55GPlatform().build(SERDESTestbench(), do_program=True)

        if arg == "grab":
            port = serial.Serial(port='/dev/ttyUSB1', baudrate=1000000)
            port.write(b"\x00")
            indent = 0

            while True:
                #while True:
                #    if port.read(1) == b'\n': break
                if port.read(1) == b'\n': break

            for x in range(CAPTURE_DEPTH):
                chars = port.read(5)
                word = 5
                try:
                    word = int(chars[:4], 16)
                except:
                    print("err " + str(chars))
                xa = word & 0b11111
                ya = (word & 0b11100000) >> 5
                if word & 0x1ff == 0x1ee:
                    #print("{}KEEEEEEEE".format(
                    #    "L" if word & (1 <<  9) else " ",
                    #), end=" ")
                    pass
                elif True: #word & (1 <<  8):
                    if xa == 27 and ya == 7:
                        print("STP")
                        indent = indent + 1
                    elif xa == 23 and ya == 7:
                        print("PAD")
                    elif xa == 29 and ya == 7:
                        print("END")
                        if indent > 0:
                            indent = indent - 1
                    elif xa == 30 and ya == 7:
                        print("EDB")
                        if indent > 0:
                            indent = indent - 1
                    elif xa == 28:
                        if ya == 0:
                            print("SKP")
                        if ya == 1:
                            print("FTS")
                        if ya == 2:
                            print("SDP")
                            indent = indent + 1
                        if ya == 3:
                            print("IDL")
                        if ya == 5:
                            print("COM")
                        if ya == 7:
                            print("EIE")
                    else:
                        print("{}{}{}{}.{}".format(" " * indent,
                            "L" if word & (1 <<  9) else " ",
                            "K" if word & (1 <<  8) else "D",
                            xa, ya,
                        ))
                # print("".join(reversed("{:010b}".format(word & 3ff)), end=" ")
                #if x % 8 == 7:
                #    print()
