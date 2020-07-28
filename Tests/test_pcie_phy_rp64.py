from nmigen import *
from nmigen.build import *
from nmigen_boards import versa_ecp5_5g as FPGA
from nmigen_stdio.serial import AsyncSerial
from ecp5_pcie.utils.utils import UARTDebugger
from ecp5_pcie.ecp5_serdes import LatticeECP5PCIeSERDES
from ecp5_pcie.serdes import K, D, Ctrl, PCIeSERDESAligner
from ecp5_pcie.layouts import ts_layout
from ecp5_pcie.phy_rx import PCIePhyRX
from ecp5_pcie.phy_tx import PCIePhyTX
from rp64_pcie_init import RP64PCIeInit

def S(x, y): return (y << 5) | x

# Usage: python test_pcie_2.py run
#        python test_pcie_2.py grab

CAPTURE_DEPTH = 4096
TS_TEST = False

class SERDESTestbench(Elaboratable):
    def __init__(self, tstest=False):
        self.tstest = tstest
    
    def elaborate(self, platform):
        m = Module()

        m.submodules.serdes = serdes = LatticeECP5PCIeSERDES(2)
        m.submodules.aligner = lane = DomainRenamer("rx")(PCIeSERDESAligner(serdes.lane))
        m.submodules.phy_rx = phy_rx = PCIePhyRX(lane)
        m.submodules.phy_tx = phy_tx = PCIePhyTX(lane)
        m.submodules.rp64init = rp64init = RP64PCIeInit("A13", "C13", Signal(), Signal(), Signal())

        #lane = serdes.lane

        m.d.comb += [
        #    serdes.txd.eq(K(28,5)),
            #lane.rx.eq(1), Crucial?
            lane.rx_invert.eq(0),
            lane.rx_align.eq(1),
        ]

        #m.domains.sync = ClockDomain()
        m.domains.rx = ClockDomain()
        m.domains.tx = ClockDomain()
        m.d.comb += [
            #ClockSignal("sync").eq(serdes.refclk),
            ClockSignal("rx").eq(serdes.rx_clk),
            ClockSignal("tx").eq(serdes.tx_clk),
        ]
        
        cntr = Signal(8)
        #m.d.tx += lane.tx_symbol.eq(Ctrl.IDL)
        #with m.FSM(domain="tx"):
        #    with m.State("1"):
        #        m.d.tx += lane.tx_symbol.eq(Ctrl.COM)
        #        m.next = "2"
        #    with m.State("2"):
        #        m.d.tx += lane.tx_symbol.eq(Ctrl.SKP)
        #        m.d.tx += cntr.eq(cntr + 1)
        #        with m.If(cntr == 3):
        #            m.d.tx += cntr.eq(0)
        #            m.next = "1"



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

        led_att1 = platform.request("led",0)
        led_att2 = platform.request("led",1)
        led_sta1 = platform.request("led",2)
        led_sta2 = platform.request("led",3)
        led_err1 = platform.request("led",4)
        led_err2 = platform.request("led",5)
        led_err3 = platform.request("led",6)
        led_err4 = platform.request("led",7)
        m.d.rx += lane.det_enable.eq(1)
        m.d.comb += [
            led_att1.eq(~(refclkcounter[25])),
            led_att2.eq(~(serdes.lane.rx_aligned)),
            led_sta1.eq(~(rxclkcounter[25])),
            led_sta2.eq(~(txclkcounter[25])),
            led_err1.eq(~(serdes.lane.rx_present)),
            led_err2.eq(~(serdes.lane.rx_locked | serdes.lane.tx_locked)),
            led_err3.eq(~(lane.det_valid)),#serdes.rxde0)),
            led_err4.eq(~(lane.det_status)),#serdes.rxce0)),
        ]
        triggered = Signal(reset = 1)
        #m.d.tx += triggered.eq((triggered ^ ((lane.rx_symbol[0:9] == Ctrl.EIE) | (lane.rx_symbol[9:18] == Ctrl.EIE))))

        uart_pins = platform.request("uart", 0)
        uart = AsyncSerial(divisor = int(100), pins = uart_pins)
        m.submodules += uart


        #m.d.rx += lane.tx_e_idle.eq(1)
        debug = UARTDebugger(uart, 4, CAPTURE_DEPTH, Cat(lane.rx_symbol[0:9], lane.rx_aligned, Signal(6), lane.rx_symbol[9:18], lane.rx_valid[0] | lane.rx_valid[1], Signal(6)), "rx", Signal()) # lane.rx_present & lane.rx_locked)
        m.submodules += debug

        m.d.sync += rp64init.init.eq(debug.running)
        with m.If(rp64init.init_sent):
            m.d.sync += debug.enable.eq(1)
        with m.Elif(~debug.running):
            m.d.sync += debug.enable.eq(0)
        
        m.d.comb += phy_tx.ts.valid.eq(1)

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
                else:
                    chars = port.read(4 * 2 + 1)
                    phi = "A"
                    for charpart in [chars[4:8], chars[:4]]: # Endianness!
                        #print("")
                        #print(charpart)
                        word = 5
                        try:
                            word = int(charpart, 16)
                        except:
                            print("err " + str(chars))
                        xa = word & 0b11111
                        ya = (word & 0b11100000) >> 5
                        print(phi, end=" ")
                        phi = "B"
                        if word & 0x1ff == 0x1ee:
                            print("E", end="")
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
                                print("{}{}{}{}.{} {}".format(" " * indent,
                                    "L" if word & (1 << 9) else " ",
                                    "K" if word & (1 << 8) else "D",
                                    xa, ya, word & 0xFF,
                                ))