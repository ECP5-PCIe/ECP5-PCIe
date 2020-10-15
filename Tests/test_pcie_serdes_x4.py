from nmigen import *
from nmigen.build import *
from nmigen_boards import versa_ecp5_5g as FPGA
from nmigen_stdio.serial import AsyncSerial
from ecp5_pcie.utils.utils import UARTDebugger
from ecp5_pcie.ecp5_serdes_geared_x4 import LatticeECP5PCIeSERDESx4
from ecp5_pcie.serdes import K, D, Ctrl, PCIeSERDESAligner
from ecp5_pcie.layouts import ts_layout
from ecp5_pcie.phy_rx import PCIePhyRX
def S(x, y): return (y << 5) | x

# Usage: python test_pcie_serdes_x4.py run
#        python test_pcie_serdes_x4.py grab
#        python test_pcie_serdes_x4.py speed # Speed test to see how good it compiles on a 45F Speed 6 device

CAPTURE_DEPTH = 256

class SERDESTestbench(Elaboratable):
    def elaborate(self, platform):
        m = Module()

        m.submodules.serdes = serdes = LatticeECP5PCIeSERDESx4(CH=1)
        m.submodules.aligner = lane = DomainRenamer("rx")(PCIeSERDESAligner(serdes.lane))

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
        
        cntr = Signal(5)
        #with m.If(cntr == 0):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.COM)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.SKP)
        #with m.Elif(cntr == 1):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.SKP)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.SKP)
        #with m.Elif(cntr == 2):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.EIE)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.EDB)
        #with m.Elif(cntr == 3):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.STP)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.SDP)
        #with m.Elif(cntr == 4):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.IDL)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.EIE)
        #with m.Elif(cntr == 5):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.EDB)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.EDB)
        #with m.Elif(cntr == 6):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.EIE)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.EIE)
        #with m.Elif(cntr == 7):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.END)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.END)
        #with m.Elif(cntr == 8):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.IDL)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.IDL)
        #with m.Else():
        #    m.d.tx += lane.tx_symbol.eq(cntr)
        with m.If(cntr[0]):
            m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.COM)
            m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.SKP)
            m.d.tx += lane.tx_symbol[18:27].eq(Ctrl.SKP)
            m.d.tx += lane.tx_symbol[27:36].eq(Ctrl.SKP)
        with m.Else():
            m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.IDL)
            m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.IDL)
            m.d.tx += lane.tx_symbol[18:27].eq(Ctrl.IDL)
            m.d.tx += lane.tx_symbol[27:36].eq(Ctrl.IDL)

        #with m.Elif(cntr == 6):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.COM)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.SKP)
        #with m.Elif(cntr == 7):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.SKP)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.SKP)
#
        #with m.Elif(cntr == 12):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.IDL)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.COM)
        #with m.Elif(cntr == 13):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.SKP)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.SKP)
        #with m.Elif(cntr == 14):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.SKP)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.IDL)
        #    
        #with m.Elif(cntr == 20):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.IDL)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.COM)
        #with m.Elif(cntr == 21):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.SKP)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.SKP)
        #with m.Elif(cntr == 22):
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.SKP)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.IDL)

        #with m.Else():
        #    m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.IDL)
        #    m.d.tx += lane.tx_symbol[9:18].eq(Ctrl.IDL)
        #m.d.tx += lane.tx_symbol[0:9].eq(Ctrl.COM)
        #m.d.tx += lane.tx_symbol[9:18].eq(cntr)
        m.d.tx += cntr.eq(cntr + 1)
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

        #refclkcounter = Signal(32)
        #m.d.sync += refclkcounter.eq(refclkcounter + 1)
        #rxclkcounter = Signal(32)
        #m.d.rx += rxclkcounter.eq(rxclkcounter + 1)
        #txclkcounter = Signal(32)
        #m.d.tx += txclkcounter.eq(txclkcounter + 1)

        leds = []
        for i in range(8):
            leds.append(platform.request("led",i))

        m.d.rx += Cat(leds).eq(lane.rx_symbol[0:8] ^ lane.rx_symbol[8:16] ^ lane.rx_symbol[16:24] ^ lane.rx_symbol[24:32] ^ Cat(lane.rx_symbol[32:36], Signal(4)))

        #m.d.rx += Cat(leds).eq(lane.rx_symbol[0:8] ^ lane.rx_symbol[24:32])
        #led_att1 = platform.request("led",0)
        #led_att2 = platform.request("led",1)
        #led_sta1 = platform.request("led",2)
        #led_sta2 = platform.request("led",3)
        #led_err1 = platform.request("led",4)
        #led_err2 = platform.request("led",5)
        #led_err3 = platform.request("led",6)
        #led_err4 = platform.request("led",7)
        #m.d.rx += lane.det_enable.eq(1)
        #m.d.comb += [
        #    led_att1.eq(~(refclkcounter[25])),
        #    led_att2.eq(~(serdes.lane.rx_aligned)),
        #    led_sta1.eq(~(rxclkcounter[25])),
        #    led_sta2.eq(~(txclkcounter[25])),
        #    led_err1.eq(~(serdes.lane.rx_present)),
        #    led_err2.eq(~(serdes.lane.rx_locked | serdes.lane.tx_locked)),
        #    led_err3.eq(~(lane.det_valid)),#serdes.rxde0)),
        #    led_err4.eq(~(lane.det_status)),#serdes.rxce0)),
        #]
        triggered = Const(1)
        #m.d.tx += triggered.eq((triggered ^ ((lane.rx_symbol[0:9] == Ctrl.EIE) | (lane.rx_symbol[9:18] == Ctrl.EIE))))

        uart_pins = platform.request("uart", 0)
        uart = AsyncSerial(divisor = int(100), pins = uart_pins)
        m.submodules += uart


        #m.d.rx += lane.tx_e_idle.eq(1)
        debug = UARTDebugger(uart, 8, CAPTURE_DEPTH, Cat(lane.rx_symbol[0:9], lane.rx_valid[0], Signal(6), lane.rx_symbol[9:18], lane.rx_valid[1], Signal(6), lane.rx_symbol[18:27], lane.rx_valid[2], Signal(6), lane.rx_symbol[27:36], lane.rx_valid[3], Signal(6)), "rx", triggered) # lane.rx_present & lane.rx_locked)
        #debug = UARTDebugger(uart, 2, CAPTURE_DEPTH, Cat(lane.rx_symbol[0:9], lane.rx_valid[0], Signal(6)), "rx", triggered) # lane.rx_present & lane.rx_locked)
        # You need to add the SERDES within the SERDES as a self. attribute for this to work
        #debug = UARTDebugger(uart, 4, CAPTURE_DEPTH, Cat(serdes.serdes.lane.rx_symbol[0:9], cntr == 0, Signal(6), Signal(9), lane.rx_valid[0] | lane.rx_valid[1], Signal(6)), "rxf", triggered) # lane.rx_present & lane.rx_locked)
        m.submodules += debug

        return m

# -------------------------------------------------------------------------------------------------

import sys
import serial


import os
os.environ["NMIGEN_ENV_Diamond"] = "/usr/local/diamond/3.11_x64/bin/lin64/diamond_env"
os.environ["NMIGEN_verbose"] = "Yes"


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        if arg == "speed":
            plat = FPGA.VersaECP55GPlatform(toolchain="Trellis")
            plat.device = "LFE5UM-45F"
            plat.speed = 6
            plat.build(SERDESTestbench(), do_program=False)

        if arg == "run":
            FPGA.VersaECP55GPlatform(toolchain="Trellis").build(SERDESTestbench(), do_program=True)

        if arg == "grab":
            port = serial.Serial(port='/dev/ttyUSB0', baudrate=1000000)
            port.write(b"\x00")
            indent = 0

            while True:
                #while True:
                #    if port.read(1) == b'\n': break
                if port.read(1) == b'\n': break

            for x in range(CAPTURE_DEPTH):
                chars = port.read(8 * 2 + 1)
                phi = "A"
                for charpart in [chars[12:16], chars[8:12], chars[4:8], chars[:4]]: # Endianness!
                    #print("")
                    #print(charpart)
                    word = 5
                    try:
                        word = int(charpart, 16)
                    except:
                        print("err " + str(chars))
                    xa = word & 0b11111
                    ya = (word & 0b11100000) >> 5
                    if phi == "B":
                        print("" + phi, end=" ")
                    else:
                        print(phi, end=" ")
                    phi = "B"
                    if word & (1 << 9):
                        print("L ", end=" ")
                    if word & 0x1ff == 0x1ee:
                        print("E")
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