from ecp5_serdes import LatticeECP5PCIeSERDES, PCIeSERDESAligner
from nmigen import *
from nmigen.build import *
from nmigen_boards import versa_ecp5_5g as FPGA
from utils.utils import UARTDebugger, Resizer
from nmigen_stdio.serial import AsyncSerial
from utils.parts import PLL1Ch

class Test(Elaboratable):
    def elaborate(self, platform):
        platform.add_resources([Resource("pcie_x1", 0,
            Subsignal("perst", Pins("A6"), Attrs(IO_TYPE="LVCMOS33")),
        )])

        m = Module()
        
        uart_pins = platform.request("uart", 0)
        uart = AsyncSerial(divisor = int(100), pins = uart_pins)

        cd_serdes       = ClockDomain()
        m.domains       += cd_serdes
        m.domains.half  = ClockDomain()
        serdes          = LatticeECP5PCIeSERDES(platform.request("pcie_x1"))
        aligner         = DomainRenamer("rx")(PCIeSERDESAligner(serdes.lane)) # The lane
        dout            = Signal(8 * 12)
        
        m.submodules    += DomainRenamer("rx")(Resizer(Cat(
            #Signal(9, reset=0xFE), Signal(6, reset=0), Signal(1, reset=1), Signal(8,reset=0),
            #Signal(9, reset=0xDC), Signal(6, reset=0), Signal(1, reset=1), Signal(8,reset=2),
            aligner.rx_symbol.word_select(0, 9), Signal(6, reset=0), aligner.rx_valid[0], serdes.lane.det_valid, serdes.lane.det_status, serdes.lane.rx_present, serdes.lane.rx_locked, serdes.lane.rx_aligned, Signal(3),
            aligner.rx_symbol.word_select(1, 9), Signal(6, reset=0), aligner.rx_valid[1], Signal(8, reset=0x11),
            ), dout, ClockSignal("half")))

        #platform.add_resources([Resource("test", 0, Pins("B19", dir="o"))]) # Arduino tx
        #m.d.comb += platform.request("test").o.eq(serdes.rx_clk_o)
        debug = UARTDebugger(uart, 12, 1000, dout, "half") # serdes.lane.rx_present & serdes.lane.rx_locked)
        m.submodules += [
            uart,
            serdes,
            aligner,
            debug,
        ]

        m.d.comb += [
            cd_serdes.clk.eq(serdes.rx_clk_o),
            serdes.rx_clk_i.eq(cd_serdes.clk),
            serdes.tx_clk_i.eq(cd_serdes.clk),
            serdes.lane.rx_align.eq(1),

            aligner.rx_align.eq(1),
        ]

        m.d.sync += serdes.lane.det_enable.eq(1)
        m.d.sync += platform.request("led", 0).o.eq(~serdes.lane.det_valid)
        m.d.sync += platform.request("led", 1).o.eq(~serdes.lane.det_status)
        m.d.sync += platform.request("led", 2).o.eq(~serdes.lane.rx_present)
        m.d.sync += platform.request("led", 3).o.eq(~serdes.lane.rx_locked)
        m.d.sync += platform.request("led", 4).o.eq(~serdes.lane.rx_aligned)
        m.d.sync += platform.request("led", 7).o.eq(~1)

        #with m.FSM():
        #    with m.State("start"):
        #        m.next = "a"
        #    with m.State("a"):
        #        m.d.sync += serdes.lane.det_enable.eq(0)
        return m

import os
os.environ["NMIGEN_verbose"] = "Yes"

if __name__ == "__main__":
    FPGA.VersaECP55GPlatform().build(Test(), do_program=True)