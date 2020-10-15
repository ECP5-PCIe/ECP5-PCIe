from nmigen import *
from nmigen.build import *
from nmigen.lib.cdc import FFSynchronizer
from nmigen_boards import versa_ecp5_5g as FPGA
from nmigen_stdio.serial import AsyncSerial
from ecp5_pcie.utils.utils import UARTDebugger
from ecp5_pcie.ecp5_phy_Gen1_x1 import LatticeECP5PCIePhy   
from ecp5_pcie.utils.parts import DTR
from ecp5_pcie.ltssm import State

# Usage: python test_pcie_phy.py run
#        python test_pcie_phy.py grab
#
# Prints data received and how long it has been in L0

CAPTURE_DEPTH = 1024

# Disable debugging for speed optimization
NO_DEBUG = False

# Default mode is to record all received symbols

class SERDESTestbench(Elaboratable):
    def elaborate(self, platform):
        m = Module()

        m.submodules.phy = ecp5_phy = LatticeECP5PCIePhy()
        phy = ecp5_phy.phy

        ltssm = phy.ltssm
        lane = phy.descrambled_lane

        # Temperature sensor, the chip gets kinda hot
        refclkcounter = Signal(32)
        m.d.sync += refclkcounter.eq(refclkcounter + 1)

        sample = Signal()
        m.d.sync += sample.eq(refclkcounter[25])
        m.submodules.dtr = dtr = DTR(start=refclkcounter[25] & ~sample)

        leds_alnum = Cat(platform.request("alnum_led", 0))

        m.d.comb += leds_alnum.eq(ltssm.debug_state)

        uart_pins = platform.request("uart", 0)
        uart = AsyncSerial(divisor = int(100), pins = uart_pins)
        m.submodules += uart
        
        platform.add_resources([Resource("test", 0, Pins("B19", dir="o"))])
        m.d.comb += platform.request("test", 0).o.eq(ClockSignal("rx"))
        platform.add_resources([Resource("test", 1, Pins("A18", dir="o"))])
        m.d.comb += platform.request("test", 1).o.eq(ClockSignal("tx"))

        if NO_DEBUG:
            pass
        else:
            # 64t 9R 9R 9T 9T 2v 4- 6D
            # t = Ticks since state was entered
            # R = RX symbol
            # T = TX symbol
            # v = RX valid
            # D = DTR Temperature, does not correspond to real temperature besides the range of 21-29 °C. After that in 10 °C steps (30 = 40 °C, 31 = 50 °C etc...), see TN1266

            time_since_state = Signal(64)
            
            with m.If(ltssm.debug_state != State.L0):
                m.d.rx += time_since_state.eq(0)
            with m.Else():
                m.d.rx += time_since_state.eq(time_since_state + 1)

            m.submodules += UARTDebugger(uart, 14, CAPTURE_DEPTH, Cat(
                time_since_state,
                lane.rx_symbol, lane.tx_symbol,
                lane.rx_locked & lane.rx_present & lane.rx_aligned, lane.rx_locked & lane.rx_present & lane.rx_aligned, Signal(4), Signal(4), phy.dll.tx.started_sending, phy.dll.tx.started_sending#dtr.temperature
                ), "rx")

        return m

# -------------------------------------------------------------------------------------------------

import sys
import serial


import os
os.environ["NMIGEN_verbose"] = "Yes"


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        if arg == "run":
            FPGA.VersaECP55GPlatform().build(SERDESTestbench(), do_program=True, nextpnr_opts="-r")

        if arg == "grab":
            port = serial.Serial(port='/dev/ttyUSB0', baudrate=1000000)
            port.write(b"\x00")
            indent = 0
            last_time = 0
            last_realtime = 0

            while True:
                #while True:
                #    if port.read(1) == b'\n': break
                if port.read(1) == b'\n': break

            # Prints a symbol as K and D codes
            def print_symbol(symbol, indent, end=""):
                xa = symbol & 0b11111
                ya = (symbol & 0b11100000) >> 5
                if symbol & 0x1ff == 0x1ee:
                    print("Error\t", end=end)

                # Convert symbol data to a string which represents it
                elif symbol & 0x100 == 0x100:
                    if xa == 27 and ya == 7:
                        print("STP\t", end=end)
                        indent = indent + 1
                    elif xa == 23 and ya == 7:
                        print("PAD\t", end=end)
                    elif xa == 29 and ya == 7:
                        print("END\t", end=end)
                        if indent > 0:
                            indent = indent - 1
                    elif xa == 30 and ya == 7:
                        print("EDB\t", end=end)
                        if indent > 0:
                            indent = indent - 1
                    elif xa == 28:
                        if ya == 0:
                            print("SKP\t", end=end)
                        if ya == 1:
                            print("FTS\t", end=end)
                        if ya == 2:
                            print("SDP\t", end=end)
                            indent = indent + 1
                        if ya == 3:
                            print("IDL\t", end=end)
                        if ya == 5:
                            print("COM\t", end=end)
                        if ya == 7:
                            print("EIE\t", end=end)
                else:
                    print("{}{}{}{}.{} \t{}".format(" " * 0 * indent,
                        "L" if symbol & (1 << 9) else " ",
                        "K" if symbol & (1 << 8) else "D",
                        xa, ya, hex(symbol & 0xFF).split("x")[1]
                    ), end=end)
                return indent

            # Returns selected bit range from a byte array
            def get_bits(word, offset, count):
                return (word & ((2 ** count - 1) << offset)) >> offset

            # Returns selected byte range from a byte array
            def get_bytes(word, offset, count):
                return (word & ((2 ** (count * 8) - 1) << (offset * 8))) >> (offset * 8)


            # The data is read into a byte array (called word) and then the relevant bits are and'ed out and right shifted.
            for x in range(CAPTURE_DEPTH):
                # 64t 9R 9R 9T 9T 2v 2-
                # t = Ticks since state was entered
                # R = RX symbol
                # T = TX symbol
                # v = RX valid
                chars = port.read(14 * 2 + 1)
                try:
                    data = int(chars, 16)
                except:
                    print("err " + str(chars))
                    data = 0
                time = get_bytes(data, 0, 8)
                symbols = [get_bits(data, 64 + 9 * i, 9) for i in range(4)]
                valid = [get_bits(data, 64 + 9 * 4, 1), get_bits(data, 33 + 9 * 4, 1)]
                print("{:{width}}".format("{:,}".format(time), width=15), end=" \t")
                for i in range(len(symbols)):
                    if i < 2:
                        print_symbol(symbols[i], 0, end="V\t" if valid[i] else "E\t")
                    else:
                        print_symbol(symbols[i], 0, end="\t")
                print(DTR.CONVERSION_TABLE[get_bits(data, 64 + 9 * 4 + 6, 6)], end=" °C\n")
