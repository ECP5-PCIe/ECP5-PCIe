from nmigen import *
from nmigen.build import *
from nmigen_boards import versa_ecp5_5g as FPGA
from nmigen_stdio.serial import AsyncSerial
from ecp5_pcie.utils.utils import UARTDebugger
from ecp5_pcie.ecp5_serdes import LatticeECP5PCIeSERDES
from ecp5_pcie.serdes import K, D, Ctrl, PCIeSERDESAligner
from ecp5_pcie.layouts import ts_layout
from ecp5_pcie.ltssm import *
def S(x, y): return (y << 5) | x

# Usage: python test_pcie_2.py run
#        python test_pcie_2.py grab

CAPTURE_DEPTH = 128
TS_TEST = False
FSM_LOG = True
#TX_TEST = False

class SERDESTestbench(Elaboratable):
    def __init__(self, tstest=False):
        self.tstest = tstest
    
    def elaborate(self, platform):
        m = Module()

        m.submodules.serdes = serdes = LatticeECP5PCIeSERDES(2) # Declare SERDES module with 1:2 gearing
        m.submodules.aligner = lane = DomainRenamer("rx")(PCIeSERDESAligner(serdes.lane)) # Aligner for aligning COM symbols
        m.submodules.phy_rx = phy_rx = PCIePhyRX(lane)
        m.submodules.phy_tx = phy_tx = PCIePhyTX(lane)
        m.submodules.ltssm = ltssm = PCIeLTSSM(lane, phy_tx, phy_rx)

        m.d.comb += [
            #lane.rx_invert.eq(0),
            lane.rx_align.eq(1),
        ]

        m.domains.rx = ClockDomain()
        m.domains.tx = ClockDomain()
        m.d.comb += [
            ClockSignal("rx").eq(serdes.rx_clk),
            ClockSignal("tx").eq(serdes.tx_clk),
        ]

        platform.add_resources([Resource("test", 0, Pins("B19", dir="o"))])
        m.d.comb += platform.request("test", 0).o.eq(ClockSignal("rx"))
        platform.add_resources([Resource("test", 1, Pins("A18", dir="o"))])
        m.d.comb += platform.request("test", 1).o.eq(ClockSignal("tx"))

        refclkcounter = Signal(32)
        m.d.sync += refclkcounter.eq(refclkcounter + 1)
        rxclkcounter = Signal(32)
        m.d.rx += rxclkcounter.eq(rxclkcounter + 1)
        txclkcounter = Signal(32)
        m.d.tx += txclkcounter.eq(txclkcounter + 1)

        detstatuscounter = Signal(7)
        with m.If(lane.det_valid & lane.det_status):
            m.d.tx += detstatuscounter.eq(detstatuscounter + 1)

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
            led_att2.eq(~(serdes.lane.rx_aligned)),
            led_sta1.eq(~(rxclkcounter[25])),
            led_sta2.eq(~(txclkcounter[25])),
            led_err1.eq(~(serdes.lane.rx_present)),
            led_err2.eq(~(serdes.lane.rx_locked | serdes.lane.tx_locked)),
            led_err3.eq(~(0)),#serdes.rxde0)),
            led_err4.eq(~(ltssm.status.link.up)),#serdes.rxce0)),
        ]
        triggered = Signal(reset = 1)
        #m.d.tx += triggered.eq((triggered ^ ((lane.rx_symbol[0:9] == Ctrl.EIE) | (lane.rx_symbol[9:18] == Ctrl.EIE))))

        uart_pins = platform.request("uart", 0)
        uart = AsyncSerial(divisor = int(100), pins = uart_pins)
        m.submodules += uart

        debug1 = Signal(16)
        debug2 = Signal(16)
        debug3 = Signal(16)
        debug4 = Signal(16)
        m.d.comb += debug1.eq(ltssm.tx_ts_count)
        m.d.comb += debug2.eq(ltssm.rx_ts_count)
        m.d.comb += debug3.eq(Cat(phy_rx.ts.valid, phy_rx.ts.lane.valid, phy_rx.ts.link.valid, phy_rx.ts.ts_id))
        m.d.comb += debug4.eq(1234)

        if self.tstest:
            # l = Link Number, L = Lane Number, v = Link Valid, V = Lane Valid, t = TS Valid, T = TS ID, n = FTS count, r = TS.rate, c = TS.ctrl, d = lane.det_status, D = lane.det_valid
            # DdTcccccrrrrrrrrnnnnnnnnLLLLLtVvllllllll
            debug = UARTDebugger(uart, 5, CAPTURE_DEPTH, Cat(phy_rx.ts.link.number, phy_rx.ts.link.valid, phy_rx.ts.lane.valid, phy_rx.ts.valid, phy_rx.ts.lane.number, phy_rx.ts.n_fts, phy_rx.ts.rate, phy_rx.ts.ctrl, phy_rx.ts.ts_id, lane.det_status, lane.det_valid), "rx") # lane.rx_present & lane.rx_locked)
            #debug = UARTDebugger(uart, 5, CAPTURE_DEPTH, Cat(ts.link.number, ts.link.valid, ts.lane.valid, ts.valid, ts.lane.number, ts.n_fts, ts.rate, ts.ctrl, ts.ts_id, Signal(2)), "rx") # lane.rx_present & lane.rx_locked)
            #debug = UARTDebugger(uart, 5, CAPTURE_DEPTH, Cat(Signal(8, reset=123), Signal(4 * 8)), "rx") # lane.rx_present & lane.rx_locked)
        elif FSM_LOG:
            time = Signal(64)
            m.d.rx += time.eq(time + 1)
            last_state = Signal(8)
            m.d.rx += last_state.eq(ltssm.debug_state)
            # oooooooo cccccccc tttttttt tttttttt tttttttt tttttttt tttttttt tttttttt tttttttt tttttttt o = old state, c = current state, t = time
            debug = UARTDebugger(uart, 10, CAPTURE_DEPTH, Cat(last_state, ltssm.debug_state, time), "rx", ltssm.debug_state != last_state, timeout=100 * 1000 * 1000)
        else:
            #if TX_TEST:
            #    debug = UARTDebugger(uart, 4, CAPTURE_DEPTH, Cat(lane.tx_symbol[0:9], Signal(7), lane.tx_symbol[9:18], Signal(3), ltssm.debug_state), "tx") # lane.rx_present & lane.rx_locked)
            #else:
            #    debug = UARTDebugger(uart, 4, CAPTURE_DEPTH, Cat(lane.rx_symbol[0:9], lane.rx_aligned, Signal(6), lane.rx_symbol[9:18], lane.rx_valid[0] | lane.rx_valid[1], Signal(2), ltssm.debug_state), "rx", triggered) # lane.rx_present & lane.rx_locked)
            # ssssssss sa000000 ssssssss sb000000 llllllll SSSSSSSS S0000000 SSSSSSSS S0000000 dddddddd dddddddd dddddddd dddddddd dddddddd dddddddd dddddddd dddddddd s = rx_symbol, S = tx_symbol, a = aligned, b = valid, l = ltssm state, d = debug
            debug = UARTDebugger(uart, 17, CAPTURE_DEPTH, Cat(lane.rx_symbol[0:9], lane.rx_aligned, Signal(6), lane.rx_symbol[9:18], lane.rx_valid[0] | lane.rx_valid[1], Signal(6), ltssm.debug_state, lane.tx_symbol[0:9], Signal(7), lane.tx_symbol[9:18], Signal(7), debug1, debug2, debug3, debug4), "rx") # lane.rx_present & lane.rx_locked)
        m.submodules += debug

        return m

# -------------------------------------------------------------------------------------------------

import sys
import serial


#import os
#os.environ["NMIGEN_verbose"] = "Yes"


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        if arg == "run":
            FPGA.VersaECP55GPlatform().build(SERDESTestbench(TS_TEST), do_program=True)

        if arg == "grab":
            port = serial.Serial(port='/dev/ttyUSB1', baudrate=1000000)
            port.write(b"\x00")
            indent = 0

            while True:
                #while True:
                #    if port.read(1) == b'\n': break
                if port.read(1) == b'\n': break

            for x in range(CAPTURE_DEPTH):
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
                    print("", end= "  " if ts_valid else "E ")
                    print("link %d" % link, end= " \t" if link_valid else "E\t")
                    print("lane %d" % lane, end= " \t" if lane_valid else "E\t")
                    print("FTS num %d" % n_fts, end= " \t")
                    print("rate %s" % bin(rate), end= " \t")
                    print("ctrl %s" % bin(ctrl), end= " \t")
                    print("TS ID %d" % (ts_id + 1), end= " \t")
                    print("Det Status %d" % det_status, end= " \t")
                    print("Det Valid %d" % det_valid)
                elif FSM_LOG:
                    # oooooooo cccccccc tttttttt tttttttt tttttttt tttttttt tttttttt tttttttt tttttttt tttttttt o = old state, c = current state, t = time
                    chars = port.read(10 * 2 + 1)
                    try:
                        data = int(chars, 16)
                    except:
                        print("err " + str(chars))
                        data = 0
                    time = (data & 0xFFFFFFFFFFFFFFFF) >> 16
                    old = data & 0xFF
                    new = (data & 0xFF00) >> 8
                    print("{:,}".format(time), end=" ")
                    print(old, end="->")
                    print(new)
                else:
                    def print_word(word, indent, end=""):
                        xa = word & 0b11111
                        ya = (word & 0b11100000) >> 5
                        if word & 0x1ff == 0x1ee:
                            print("Error\t", end=end)
                        elif True: #word & (1 <<  8):
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
                                    "L" if word & (1 << 9) else " ",
                                    "K" if word & (1 << 8) else "D",
                                    xa, ya, word & 0xFF
                                ), end=end)
                        return indent
                    # ssssssss sa000000 ssssssss sb000000 llllllll SSSSSSSS S0000000 SSSSSSSS S0000000 dddddddd dddddddd dddddddd dddddddd dddddddd dddddddd dddddddd dddddddd s = rx_symbol, S = tx_symbol, a = aligned, b = valid, l = ltssm state, d = debug
                    chars = port.read(17 * 2 + 1)
                    try:
                        data = int(chars, 16)
                    except:
                        print("err " + str(chars))
                        data = 0
                    print("RX:", end="\t")
                    indent = print_word(data & 0x3FF, indent, end=" \t")
                    indent = print_word((data & 0x3FF0000) >> 16, indent, end=" \t")
                    print("TX:", end="\t")
                    indent = print_word((data & 0x3FF0000000000) >> 40, indent, end=" \t")
                    indent = print_word((data & 0x3FF00000000000000) >> 56, indent, end=" \t")
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
