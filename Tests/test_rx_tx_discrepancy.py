from amaranth import *
from amaranth.build import *
from amaranth_boards import versa_ecp5_5g as FPGA
from amaranth_stdio.serial import AsyncSerial
from ecp5_pcie.utils.utils import UARTDebugger
from ecp5_pcie.ecp5_serdes import LatticeECP5PCIeSERDES
from ecp5_pcie.serdes import K, D, Ctrl, PCIeSERDESAligner

# Usage: python test_rx_tx_discrepancy.py run
#        python test_rx_tx_discrepancy.py grab

CAPTURE_DEPTH = 4096

class SERDESTestbench(Elaboratable):
    def __init__(self, tstest=False):
        self.tstest = tstest
    
    def elaborate(self, platform):
        m = Module()

        m.submodules.serdes = serdes = LatticeECP5PCIeSERDES(2)
        m.submodules.aligner = lane = DomainRenamer("rx")(PCIeSERDESAligner(serdes.lane))
        m.d.comb += [
            lane.rx_invert.eq(0),
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

        led_att1 = platform.request("led",0)
        led_att2 = platform.request("led",1)
        led_sta1 = platform.request("led",2)
        led_sta2 = platform.request("led",3)
        led_err1 = platform.request("led",4)
        led_err2 = platform.request("led",5)
        led_err3 = platform.request("led",6)
        led_err4 = platform.request("led",7)
        #m.d.comb += [
        #    led_att1.eq(~(ClockSignal("rx") ^ ClockSignal("tx"))),
        #]

        count = Signal()
        refclkcounter = Signal(64)
        txclkcounter = Signal(64)
        rxclkcounter = Signal(64)
        with m.If(count):
            m.d.sync += refclkcounter.eq(refclkcounter + 1)
            m.d.tx += txclkcounter.eq(txclkcounter + 1)
            m.d.rx += rxclkcounter.eq(rxclkcounter + 1)

        counter = Signal(16)
        sample = Signal()
        with m.FSM():
            with m.State("Wait"):
                m.d.sync += count.eq(1)
                m.d.sync += counter.eq(counter + 1)
                with m.If(counter == 0xFFFF):
                    m.d.sync += count.eq(0)
                    m.d.sync += counter.eq(0)
                    m.next = "Sample Delay"
            with m.State("Sample Delay"):
                m.d.sync += counter.eq(counter + 1)
                with m.If(counter == 0xF):
                    m.d.sync += counter.eq(0)
                    m.next = "Sample"
            with m.State("Sample"):
                m.d.sync += sample.eq(1)
                m.next = "Sample After Delay"
            with m.State("Sample After Delay"):
                m.d.sync += sample.eq(0)
                m.d.sync += counter.eq(counter + 1)
                with m.If(counter == 0xF):
                    m.d.sync += counter.eq(0)
                    m.next = "Wait"
        
        uart_pins = platform.request("uart", 0)
        uart = AsyncSerial(divisor = int(100), pins = uart_pins)
        m.submodules += uart
        debug = UARTDebugger(uart, 8 * 3, CAPTURE_DEPTH, Cat(refclkcounter, txclkcounter, rxclkcounter), "sync", sample) # lane.rx_present & lane.rx_locked)
        m.submodules += debug

        return m

# -------------------------------------------------------------------------------------------------

import sys
import serial


import os
os.environ["AMARANTH_verbose"] = "Yes"


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        if arg == "run":
            FPGA.VersaECP55GPlatform().build(SERDESTestbench(), do_program=True)

        if arg == "grab":
            port = serial.Serial(port='/dev/ttyUSB1', baudrate=1000000)
            port.write(b"\x00")
            indent = 0

            while True:
                if port.read(1) == b'\n': break

            chars = port.read(8 * 3 * 2 + 1)
            wordrx_old = int(chars[0:16], 16)
            wordtx_old = int(chars[16:32], 16)
            wordref_old = int(chars[32:48], 16)

            max_rx_tx = 0
            max_rel = 0

            for x in range(CAPTURE_DEPTH - 1):
                chars = port.read(8 * 3 * 2 + 1)
                wordrx = int(chars[0:16], 16)
                wordtx = int(chars[16:32], 16)
                wordref = int(chars[32:48], 16)

                wordrx_delta = wordrx - wordrx_old
                wordtx_delta = wordtx - wordtx_old
                wordref_delta = wordref - wordref_old

                max_rx_tx = max(max_rx_tx, abs(wordrx_delta - wordtx_delta))
                max_rel = max(max_rel, abs((wordrx_delta - wordtx_delta) / (wordrx_delta * 0.01)))

                print("RX: %d" % wordrx_delta, end= " \t")
                print("TX: %d" % wordtx_delta, end= " \t")
                print("Sync: %d" % wordref_delta, end= " \t")
                print("RX-TX: %d" % (wordrx_delta - wordtx_delta), end= " \t")
                print("Rel: %f%%" % ((wordrx_delta - wordtx_delta) / (wordrx_delta * 0.01)), end= " \t")
                print("RX-TX max: %d" % max_rx_tx, end= " \t")
                print("Rel max: %f%%" % max_rel)

                wordrx_old = wordrx
                wordtx_old = wordtx
                wordref_old = wordref