from nmigen import *
from nmigen.build import *
from nmigen.lib.cdc import FFSynchronizer
from nmigen_boards import versa_ecp5_5g as FPGA
from nmigen_stdio.serial import AsyncSerial
from ecp5_pcie.utils.utils import UARTDebugger
from ecp5_pcie.ecp5_serdes_geared_x4 import LatticeECP5PCIeSERDESx4
from ecp5_pcie.serdes import K, D, Ctrl, PCIeSERDESAligner, PCIeSERDESInterface, PCIeScrambler
from ecp5_pcie.layouts import ts_layout
from ecp5_pcie.ltssm import *
from ecp5_pcie.utils.parts import DTR
from ecp5_pcie.lfsr import PCIeLFSR

# Usage: python test_pcie_ltssm.py run
#        python test_pcie_ltssm.py grab

CAPTURE_DEPTH = 1024

# Disable debugging for speed optimization
NO_DEBUG = False

# Record TS
TS_TEST = False

# Record a State
STATE_TEST = False
TESTING_STATE = State.L0

# Record LTSSM state transitions
FSM_LOG = True

# Default mode is to record all received symbols

class SERDESTestbench(Elaboratable):
    def __init__(self, tstest=False):
        self.tstest = tstest
    
    def elaborate(self, platform):
        m = Module()

        # Received symbols are aligned and processed by the PCIePhyRX
        # The PCIePhyTX sends symbols to the SERDES
        m.submodules.serdes = serdes = LatticeECP5PCIeSERDESx4(speed_5GTps=False) # Declare SERDES module with 1:2 gearing
        m.submodules.aligner = aligner = DomainRenamer("rx")(PCIeSERDESAligner(serdes.lane)) # Aligner for aligning COM symbols
        m.submodules.scrambler = lane = PCIeScrambler(aligner) # Aligner for aligning COM symbols
        #lane = serdes.lane # Aligner for aligning COM symbols
        m.submodules.phy_rx = phy_rx = PCIePhyRX(aligner, lane)
        m.submodules.phy_tx = phy_tx = PCIePhyTX(lane)
        #m.submodules.lfsr = lfsr = PCIeLFSR(0, 1)
        #m.submodules.phy_txfake = phy_txfake = PCIePhyTX(PCIeSERDESInterface(ratio = 2))

        # Link Status Machine to test
        #m.submodules.ltssm = ltssm = PCIeLTSSM(lane, phy_tx, phy_rx)
        m.submodules.ltssm = ltssm = PCIeLTSSM(lane, phy_tx, phy_rx)
        #m.d.comb += [
        #    phy_tx.ts.eq(0),
        #    phy_tx.ts.valid.eq(1),
        #    phy_tx.ts.rate.eq(1),
        #    phy_tx.ts.ctrl.eq(0)
        #]
        
        m.d.rx += lane.enable.eq(ltssm.status.link.scrambling & ~phy_tx.sending_ts)

        m.d.comb += [
            #lane.rx_invert.eq(0),
            serdes.lane.rx_align.eq(1),
        ]

        m.d.comb += [
            #lane.rx_invert.eq(0),
            lane.rx_align.eq(1),
        ]

        # Declare the RX and TX clock domain, most of the logic happens in the RX domain
        m.domains.rx = ClockDomain()
        m.domains.tx = ClockDomain()
        m.d.comb += [
            ClockSignal("rx").eq(serdes.rx_clk),
            ClockSignal("tx").eq(serdes.tx_clk),
        ]

        # Clock outputs for the RX and TX clock domain
        #platform.add_resources([Resource("test", 0, Pins("B19", dir="o"))])
        #m.d.comb += platform.request("test", 0).o.eq(ClockSignal("rx"))
        #platform.add_resources([Resource("test", 1, Pins("A18", dir="o"))])
        #m.d.comb += platform.request("test", 1).o.eq(ClockSignal("tx"))

        # Counters for the LEDs
        refclkcounter = Signal(32)
        m.d.sync += refclkcounter.eq(refclkcounter + 1)
        rxclkcounter = Signal(32)
        m.d.rx += rxclkcounter.eq(rxclkcounter + 1)
        txclkcounter = Signal(32)
        m.d.tx += txclkcounter.eq(txclkcounter + 1)

        #m.d.rx += serdes.slip.eq(rxclkcounter[25])
        
        ## Sample temperature once a second
        #m.d.sync += dtr.start.eq(refclkcounter[25])

        # Temperature sensor, the chip gets kinda hot
        sample = Signal()
        m.d.sync += sample.eq(refclkcounter[25])
        m.submodules.dtr = dtr = DTR(start=refclkcounter[25] & ~sample)

        # Can be used to count how many cycles det_status is on, currently unused
        detstatuscounter = Signal(7)
        with m.If(lane.det_valid & lane.det_status):
            m.d.tx += detstatuscounter.eq(detstatuscounter + 1)

        leds = Cat(platform.request("led", i) for i in range(8))
        leds_alnum = Cat(platform.request("alnum_led", 0))

        # Information LEDs, first three output the clock frequency of the clock domains divided by 2^26
        #m.d.comb += [
        #    leds[0].eq(~(refclkcounter[25])),
        #    leds[2].eq(~(rxclkcounter[25])),
        #    leds[3].eq(~(txclkcounter[25])),
        #    leds[1].eq(~(serdes.lane.rx_aligned)),
        #    leds[4].eq(~(serdes.lane.rx_present)),
        #    leds[5].eq(~(serdes.lane.rx_locked | serdes.lane.tx_locked)),
        #    leds[6].eq(~(0)),#serdes.rxde0)),
        #    leds[7].eq(~(ltssm.status.link.up)),#serdes.rxce0)),
        #]

        m.d.comb += leds_alnum.eq(ltssm.debug_state)
        m.d.comb += leds.eq(~ltssm.debug_state)

        uart_pins = platform.request("uart", 0)
        uart = AsyncSerial(divisor = int(100), pins = uart_pins)
        m.submodules += uart

        # In the default mode, there are some extra words for debugging data
        debug1 = Signal(16)
        debug2 = Signal(16)
        debug3 = Signal(16)
        debug4 = Signal(16)
        
        # For example data from the LTSSM
        m.d.comb += debug1.eq(ltssm.tx_ts_count)
        m.d.comb += debug2.eq(ltssm.rx_ts_count)
        # Or data about TSs
        m.d.comb += debug3.eq(Cat(phy_rx.ts.valid, phy_rx.ts.lane.valid, phy_rx.ts.link.valid, phy_rx.ts.ts_id))
        m.d.comb += debug4.eq(1234)

        if NO_DEBUG:
            pass
        if self.tstest:
            # l = Link Number, L = Lane Number, v = Link Valid, V = Lane Valid, t = TS Valid, T = TS ID, n = FTS count, r = TS.rate, c = TS.ctrl, d = lane.det_status, D = lane.det_valid
            # DdTcccccrrrrrrrrnnnnnnnnLLLLLtVvllllllll
            debug = UARTDebugger(uart, 5, CAPTURE_DEPTH, Cat(phy_rx.ts.link.number, phy_rx.ts.link.valid, phy_rx.ts.lane.valid, phy_rx.ts.valid, phy_rx.ts.lane.number, phy_rx.ts.n_fts, phy_rx.ts.rate, phy_rx.ts.ctrl, phy_rx.ts.ts_id, lane.det_status, lane.det_valid), "rx") # lane.rx_present & lane.rx_locked)
            #debug = UARTDebugger(uart, 5, CAPTURE_DEPTH, Cat(ts.link.number, ts.link.valid, ts.lane.valid, ts.valid, ts.lane.number, ts.n_fts, ts.rate, ts.ctrl, ts.ts_id, Signal(2)), "rx") # lane.rx_present & lane.rx_locked)
            #debug = UARTDebugger(uart, 5, CAPTURE_DEPTH, Cat(Signal(8, reset=123), Signal(4 * 8)), "rx") # lane.rx_present & lane.rx_locked)
        
        elif STATE_TEST:
            # 32t 9R 9R 9T 9T 2v 2-
            # t = Ticks since state was entered
            # R = RX symbol
            # T = TX symbol
            # v = RX valid

            time_since_state = Signal(32)
            
            with m.If(ltssm.debug_state != TESTING_STATE):
                m.d.rx += time_since_state.eq(0)
            with m.Else():
                m.d.rx += time_since_state.eq(time_since_state + 1)
            #m.d.rx += time_since_state.eq(ltssm.status.link.scrambling)
            #m.d.rx += time_since_state.eq(ltssm.rx_idl_count_total)
            #m.d.rx += time_since_state.eq(Cat(phy_rx.inverted, lane.rx_invert))

            debug = UARTDebugger(uart, 9, CAPTURE_DEPTH, Cat(
                time_since_state,
                lane.rx_symbol, lane.tx_symbol,
                lane.rx_locked & lane.rx_present & lane.rx_aligned, lane.rx_locked & lane.rx_present & lane.rx_aligned, Signal(2)
                ), "rx")#, (ltssm.debug_state == TESTING_STATE) & (time_since_state < CAPTURE_DEPTH), timeout=100 * 1000 * 1000)

        elif FSM_LOG:
            # Keep track of time in 8 nanosecond increments
            time = Signal(64)
            m.d.rx += time.eq(time + 1)

            # Real time in 10 ns ticks, doesnt drift or change in frequency as compared to the RX clock domain.
            realtime = Signal(64)
            m.d.sync += realtime.eq(realtime + 1)

            # Real time FF sync
            realtime_rx = Signal(64)
            m.submodules += FFSynchronizer(realtime, realtime_rx, o_domain="rx")

            last_state = Signal(8)
            m.d.rx += last_state.eq(ltssm.debug_state)
            # 8o 8c 64t 64r 32i 6T 1v 1- 8l 5L o O 1-
            # o = old state, c = current state, t = time, r = realtime, i = idle count, T = temperature, v = temperature valid, - = empty, l = link, L = lane, o = link valid, O = lane valid
            # preceding number is number of bits
            debug = UARTDebugger(uart, 25, CAPTURE_DEPTH, Cat(
                last_state, ltssm.debug_state, time, realtime_rx, Signal(32), dtr.temperature, Signal(1), dtr.valid,
                phy_rx.ts.link.number, phy_rx.ts.lane.number, phy_rx.ts.link.valid, phy_rx.ts.lane.valid, Signal(1)
                ), "rx", ltssm.debug_state != last_state, timeout=100 * 1000 * 1000)
        
        else:
            # ssssssss sa000000 ssssssss sb000000 llllllll SSSSSSSS S0000000 SSSSSSSS S0000000 dddddddd dddddddd dddddddd dddddddd dddddddd dddddddd dddddddd dddddddd s = rx_symbol, S = tx_symbol, a = aligned, b = valid, l = ltssm state, d = debug
            debug = UARTDebugger(uart, 17, CAPTURE_DEPTH, Cat(lane.rx_symbol[0:9], lane.rx_aligned, Signal(6), lane.rx_symbol[9:18], lane.rx_valid[0] | lane.rx_valid[1], Signal(6), ltssm.debug_state, lane.tx_symbol[0:9], Signal(7), lane.tx_symbol[9:18], Signal(7), debug1, debug2, debug3, debug4), "rx") # lane.rx_present & lane.rx_locked)
        m.submodules += debug

        return m

# -------------------------------------------------------------------------------------------------

import sys
import serial
from glob import glob


import os
os.environ["NMIGEN_verbose"] = "Yes"


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        if arg == "run":
            FPGA.VersaECP55GPlatform().build(SERDESTestbench(TS_TEST), do_program=True, nextpnr_opts="-r")

        if arg == "grab":
            port = serial.Serial(port=glob("/dev/serial/by-id/usb-FTDI_Lattice_ECP5_5G_VERSA_Board_*-if01-port0")[0], baudrate=1000000)
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
                elif True:
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

                # Outputs received TSs
                if TS_TEST:
                    # l = Link Number, L = Lane Number, v = Link Valid, V = Lane Valid, t = TS Valid, T = TS ID, n = FTS count, r = TS.rate, c = TS.ctrl, d = lane.det_status, D = lane.det_valid
                    # DdTcccccrrrrrrrrnnnnnnnnLLLLLtVvllllllll
                    chars = port.read(5 * 2 + 1)
                    word = int(chars, 16)

                    link = word & 0xFF
                    link_valid = (word & 0x100) == 0x100
                    lane_valid = (word & 0x200) == 0x200
                    ts_valid = (word & 0x400) == 0x400
                    lane = (word & 0xF800) >> 11
                    n_fts = (word & 0xFF0000) >> 16
                    rate = (word & 0xFF000000) >> 24
                    ctrl = (word & 0x1F00000000) >> 32
                    ts_id = (word & 0x2000000000) >> 37
                    det_status = (word & 0x4000000000) == 0x4000000000
                    det_valid = (word & 0x8000000000) == 0x8000000000
                    print("", end= "TS valid     " if ts_valid else "TS invalid   ")
                    print("link %d" % link, end= " \t" if link_valid else "E\t")
                    print("lane %d" % lane, end= " \t" if lane_valid else "E\t")
                    print("FTS num %d" % n_fts, end= " \t")
                    print("rate %s" % bin(rate), end= " \t")
                    print("ctrl %s" % bin(ctrl), end= " \t")
                    print("TS ID %d" % (ts_id + 1), end= " \t")
                    print("Det Status %d" % det_status, end= " \t")
                    print("Det Valid %d" % det_valid)

                # Displays symbols received during a state
                elif STATE_TEST:
                    # 32t 9R 9R 9T 9T 2v 2-
                    # t = Ticks since state was entered
                    # R = RX symbol
                    # T = TX symbol
                    # v = RX valid
                    chars = port.read(9 * 2 + 1)
                    try:
                        data = int(chars, 16)
                    except:
                        print("err " + str(chars))
                        data = 0
                    time = get_bytes(data, 0, 4)
                    symbols = [get_bits(data, 32 + 9 * i, 9) for i in range(4)]
                    valid = [get_bits(data, 32 + 9 * 4, 1), get_bits(data, 33 + 9 * 4, 1)]
                    print("{:{width}}".format("{:,}".format(time), width=15), end=" \t")
                    for i in range(len(symbols)):
                        if i < 2:
                            print_symbol(symbols[i], 0, end="V\t" if valid[i] else "E\t")
                        else:
                            print_symbol(symbols[i], 0, end="\t" if i < 3 else "\n")

                # Displays the log of LTSSM state transitions
                elif FSM_LOG:
                    # 8o 8c 64t 64r 32i 6T 1v 1- 8l 5L o O 1-
                    # o = old state, c = current state, t = time, r = realtime, i = idle count, T = temperature, v = temperature valid, - = empty, l = link, L = lane, o = link valid, O = lane valid
                    # preceding number is number of bits
                    chars = port.read(25 * 2 + 1)
                    try:
                        data = int(chars, 16)
                    except:
                        print("err " + str(chars))
                        data = 0
                    old = get_bytes(data, 0, 1)
                    new = get_bytes(data, 1, 1)
                    time = get_bytes(data, 2, 8)
                    realtime = get_bytes(data, 10, 8)
                    idl = get_bytes(data, 18, 4)
                    temp = get_bits(data, 22 * 8, 6)
                    link = get_bytes(data, 23, 1)
                    lane = get_bits(data, 24 * 8, 5)
                    link_valid = get_bits(data, 24 * 8 + 5, 1)
                    lane_valid = get_bits(data, 24 * 8 + 6, 1)
                    print("{:,}".format(temp), end=" \t")
                    print("{:{width}}".format("{:,}"    .format(realtime), width=15)                       , end=" \t")
                    print("{:{width}}".format("{:,} ns" .format((realtime - last_realtime) * 10), width=12), end=" \t")
                    print("{:{width}}".format("{:,}"    .format(time), width=15)                           , end=" \t")
                    print("{:{width}}".format("{:,} ns" .format((time - last_time) * 8), width=12)         , end=" \t")
                    print("{:,}".format(link), end="V\t" if link_valid else " \t")
                    print("{:,}".format(lane), end="V\t" if lane_valid else " \t")
                    print(State(old).name, end="->")
                    print(State(new).name, end=" ")
                    print(idl, end="\n\n" if new == State.Detect_Quiet else "\n")
                    last_time = time
                    last_realtime = realtime

                else:
                    
                    # ssssssss sa000000 ssssssss sb000000 llllllll SSSSSSSS S0000000 SSSSSSSS S0000000 dddddddd dddddddd dddddddd dddddddd dddddddd dddddddd dddddddd dddddddd s = rx_symbol, S = tx_symbol, a = aligned, b = valid, l = ltssm state, d = debug
                    chars = port.read(17 * 2 + 1)
                    try:
                        data = int(chars, 16)
                    except:
                        print("err " + str(chars))
                        data = 0
                    print("RX:", end="\t")
                    indent = print_symbol(data & 0x3FF, indent, end=" \t")
                    indent = print_symbol((data & 0x3FF0000) >> 16, indent, end=" \t")
                    print("TX:", end="\t")
                    indent = print_symbol((data & 0x3FF0000000000) >> 40, indent, end=" \t")
                    indent = print_symbol((data & 0x3FF00000000000000) >> 56, indent, end=" \t")
                    print("LTSSM:", end="\t")
                    print((data & 0xFF00000000) >> 32, end="\t")
                    print("DEBUG1:", end="\t")
                    print((data & 0xFFFF000000000000000000) >> 72, end="\t")
                    print("DEBUG2:", end="\t")
                    print((data & 0xFFFF0000000000000000000000) >> 88, end="\t")
                    print("DEBUG3:", end="\t")
                    print(bin((data & 0xFFFF00000000000000000000000000) >> 104), end="\t")
                    print("DEBUG4:", end="\t")
                    print((data & 0xFFFF000000000000000000000000000000) >> 120)
