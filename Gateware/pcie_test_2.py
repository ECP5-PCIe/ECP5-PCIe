from nmigen import *
from nmigen.build import *
from nmigen_boards import versa_ecp5_5g as FPGA
from nmigen.lib.cdc import FFSynchronizer as MultiReg
from nmigen_stdio.serial import AsyncSerial
from utils.utils import UARTDebugger
from ecp5_serdes import LatticeECP5PCIeSERDES
from serdes import K, D, Ctrl, PCIeSERDESAligner
from layouts import ts_layout
def S(x, y): return (y << 5) | x

# Usage: python pcie_test_2.py run
#        python pcie_test_2.py grab

CAPTURE_DEPTH = 4096

class SERDESTestbench(Elaboratable):
    def elaborate(self, platform):
        m = Module()

        m.submodules.serdes = serdes = LatticeECP5PCIeSERDES(2)
        m.submodules.aligner = lane = DomainRenamer("rx")(PCIeSERDESAligner(serdes.lane))
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
        with m.FSM(domain="tx"):
            with m.State("1"):
                m.d.tx += lane.tx_symbol.eq(Ctrl.COM)
                m.next = "2"
            with m.State("2"):
                m.d.tx += lane.tx_symbol.eq(Ctrl.SKP)
                m.d.tx += cntr.eq(cntr + 1)
                with m.If(cntr == 3):
                    m.d.tx += cntr.eq(0)
                    m.next = "1"

        ts = Record(ts_layout)
        symbol1 = lane.rx_symbol[0: 9]
        symbol2 = lane.rx_symbol[9:18]
        inverted = Signal()

        with m.FSM(domain="rx"): # TODO: Check if ts changes between consecutive ordered sequences and only accept if it does not
            with m.State("COMMA"):
                with m.If(symbol1 == Ctrl.COM):
                    with m.If(symbol2 == Ctrl.PAD):
                        m.d.rx += ts.link.valid.eq(0)
                        m.next = "TSn-LANE"
                    with m.If(symbol2 == Ctrl.SKP):
                        m.next = "SKP"
                    with m.If(symbol2[8] == 0):
                        m.d.rx += ts.link.number.eq(symbol2[:8])
                        m.d.rx += ts.link.valid.eq(1)
                        m.next = "TSn-LANE" # Ignore the comma otherwise, could be a different ordered set
            with m.State("SKP"): # SKP ordered set, in COMMA there is 'COM SKP' and here is 'SKP SKP' in rx_symbol, after which it goes back to COMMA.
                m.next = "COMMA"
            with m.State("TSn-LANE"):
                m.next = "TSn-DATA"
                with m.If(symbol2[8] == 0):
                    m.d.rx += ts.n_fts.eq(symbol2[:8])
                with m.If(symbol1 == Ctrl.PAD):
                    m.d.rx += ts.lane.valid.eq(0)
                with m.If(symbol1[8] == 0):
                    m.d.rx += ts.lane.number.eq(symbol1[:5])
            with m.State("TSn-DATA"):
                m.next = "TSn-ID0"
                with m.If(symbol1[8] == 0):
                    m.d.rx += Cat(ts.rate).eq(symbol1[:8])
                with m.If(symbol2[8] == 0):
                    m.d.rx += Cat(ts.ctrl).eq(symbol2[:5])
            for i in range(4):
                with m.State("TSn-ID%d" % i):
                    m.next = "TSn-ID%d" % (i + 1)
                    with m.If(symbol1 == D(10,2)):
                        m.d.rx += ts.ts_id.eq(0)
                    with m.If(symbol1 == D(5,2)):
                        m.d.rx += ts.ts_id.eq(1)
                    with m.If(symbol1 == D(21,5)):
                        m.d.rx += ts.ts_id.eq(0)
                        m.d.rx += inverted.eq(1)
                    with m.If(symbol1 == D(26,5)):
                        m.d.rx += ts.ts_id.eq(1)
                        m.d.rx += inverted.eq(1)
            with m.State("TSn-ID4"):
                m.next = "COMMA"
                with m.If(inverted):
                    lane.rx_invert.eq(~lane.rx_invert)



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
        m.d.comb += [
            led_att1.eq(~(refclkcounter[25])),
            led_att2.eq(~(serdes.lane.rx_aligned)),
            led_sta1.eq(~(rxclkcounter[25])),
            led_sta2.eq(~(txclkcounter[25])),
            led_err1.eq(~(serdes.lane.rx_present)),
            led_err2.eq(~(serdes.lane.rx_locked | serdes.lane.tx_locked)),
            led_err3.eq(~(0)),#serdes.rxde0)),
            led_err4.eq(~(0)),#serdes.rxce0)),
        ]
        triggered = Signal(reset = 1)
        #m.d.tx += triggered.eq((triggered ^ ((lane.rx_symbol[0:9] == Ctrl.EIE) | (lane.rx_symbol[9:18] == Ctrl.EIE))))

        uart_pins = platform.request("uart", 0)
        uart = AsyncSerial(divisor = int(100), pins = uart_pins)
        m.submodules += uart
        debug = UARTDebugger(uart, 4, CAPTURE_DEPTH, Cat(lane.rx_symbol[0:9], lane.rx_aligned, Signal(6), lane.rx_symbol[9:18], lane.rx_valid[0] | lane.rx_valid[1], Signal(6)), "rx", triggered) # lane.rx_present & lane.rx_locked)
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
                chars = port.read(9)
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
