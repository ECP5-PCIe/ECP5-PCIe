from amaranth import *
from amaranth.build import *
from amaranth.lib.cdc import FFSynchronizer, AsyncFFSynchronizer
from amaranth.lib.fifo import AsyncFIFOBuffered, AsyncFIFO
from .serdes import PCIeSERDESInterface, K, Ctrl
from .ecp5_serdes import LatticeECP5PCIeSERDES


__all__ = ["LatticeECP5PCIeSERDESx2"]


class LatticeECP5PCIeSERDESx2(Elaboratable): # Based on Yumewatari
    def __init__(self):

        self.rx_clk = Signal()  # recovered word clock

        self.tx_clk = Signal()  # generated word clock

        # The PCIe lane with all signals necessary to control it
        self.lane = PCIeSERDESInterface(2)

        # Bit Slip
        self.slip = Signal()
    
    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        m.submodules.serdes = serdes = LatticeECP5PCIeSERDES(1)
        m.submodules += self.lane

        m.domains.rxf = ClockDomain()
        m.domains.txf = ClockDomain()
        m.d.comb += [
            #ClockSignal("sync").eq(serdes.refclk),
            ClockSignal("rxf").eq(serdes.rx_clk),
            ClockSignal("txf").eq(serdes.tx_clk),
        ]

        platform.add_clock_constraint(self.rx_clk, 125e6) # For NextPNR, set the maximum clock frequency such that errors are given
        platform.add_clock_constraint(self.tx_clk, 125e6)

        m.submodules.lane = lane = PCIeSERDESInterface(2)

        self.lane.frequency = int(125e6)

        # IF SOMETHING IS BROKE: Check if the TX actually transmits good data and not order-swapped data
        m.d.rxf += self.rx_clk.eq(~self.rx_clk)
        with m.If(~self.rx_clk):
            m.d.rxf += lane.rx_symbol[9:18].eq(serdes.lane.rx_symbol)
            m.d.rxf += lane.rx_valid[1].eq(serdes.lane.rx_valid)
        with m.Else():
            m.d.rxf += lane.rx_symbol[0:9].eq(serdes.lane.rx_symbol)
            m.d.rxf += lane.rx_valid[0].eq(serdes.lane.rx_valid)

            # To ensure that it outputs consistent data
            # m.d.rxf += self.lane.rx_symbol.eq(lane.rx_symbol)
            # m.d.rxf += self.lane.rx_valid.eq(lane.rx_valid)

        m.d.txf += self.tx_clk.eq(~self.tx_clk)
        # Do NOT add an invert here! It works, checked with x1 gearing. If you do, a "COM SKP SKP SKP" will turn into a "SKP COM SKP SKP"
        #with m.If(self.tx_clk):
        #    m.d.txf += serdes.lane.tx_symbol    .eq(lane.tx_symbol[9:18])
        #    m.d.txf += serdes.lane.tx_disp      .eq(lane.tx_disp[1])
        #    m.d.txf += serdes.lane.tx_set_disp  .eq(lane.tx_set_disp[1])
        #    m.d.txf += serdes.lane.tx_e_idle    .eq(lane.tx_e_idle[1])
        #with m.Else():
        #    m.d.txf += serdes.lane.tx_symbol    .eq(lane.tx_symbol[0:9])
        #    m.d.txf += serdes.lane.tx_disp      .eq(lane.tx_disp[0])
        #    m.d.txf += serdes.lane.tx_set_disp  .eq(lane.tx_set_disp[0])
        #    m.d.txf += serdes.lane.tx_e_idle    .eq(lane.tx_e_idle[0])

            # To ensure that it inputs consistent data
            # m.d.rxf += lane.tx_symbol.eq(self.lane.tx_symbol)
            # m.d.rxf += lane.tx_disp.eq(self.lane.tx_disp)
            # m.d.rxf += lane.tx_set_disp.eq(self.lane.tx_set_disp)
            # m.d.rxf += lane.tx_e_idle.eq(self.lane.tx_e_idle)

        m.d.txf += serdes.lane.tx_symbol    .eq(Mux(self.tx_clk, lane.tx_symbol[9:18],  lane.tx_symbol[0:9]))
        m.d.txf += serdes.lane.tx_disp      .eq(Mux(self.tx_clk, lane.tx_disp[1],       lane.tx_disp[0]))
        m.d.txf += serdes.lane.tx_set_disp  .eq(Mux(self.tx_clk, lane.tx_set_disp[1],   lane.tx_set_disp[0]))
        m.d.txf += serdes.lane.tx_e_idle    .eq(Mux(self.tx_clk, lane.tx_e_idle[1],     lane.tx_e_idle[0]))


        # CDC
        rx_fifo = m.submodules.rx_fifo = AsyncFIFOBuffered(width=20, depth=4, r_domain="rx", w_domain="rxf")
        m.d.rxf += rx_fifo.w_data.eq(Cat(lane.rx_symbol, lane.rx_valid))
        m.d.comb += Cat(self.lane.rx_symbol, self.lane.rx_valid).eq(rx_fifo.r_data)
        m.d.comb += rx_fifo.r_en.eq(1)
        m.d.rxf += rx_fifo.w_en.eq(self.rx_clk)

        tx_fifo = m.submodules.tx_fifo = AsyncFIFOBuffered(width=24, depth=4, r_domain="txf", w_domain="tx")
        m.d.comb += tx_fifo.w_data.eq(Cat(self.lane.tx_symbol, self.lane.tx_set_disp, self.lane.tx_disp, self.lane.tx_e_idle))
        m.d.txf  += Cat(lane.tx_symbol, lane.tx_set_disp, lane.tx_disp, lane.tx_e_idle).eq(tx_fifo.r_data)
        m.d.txf  += tx_fifo.r_en.eq(self.tx_clk)
        m.d.comb += tx_fifo.w_en.eq(1)
        #m.d.txf  += Cat(lane.tx_symbol, lane.tx_set_disp, lane.tx_disp, lane.tx_e_idle).eq(Cat(self.lane.tx_symbol, self.lane.tx_set_disp, self.lane.tx_disp, self.lane.tx_e_idle))


        serdes.lane.rx_invert     = self.lane.rx_invert
        serdes.lane.rx_align      = self.lane.rx_align
        serdes.lane.rx_aligned    = self.lane.rx_aligned
        serdes.lane.rx_locked     = self.lane.rx_locked
        serdes.lane.rx_present    = self.lane.rx_present

        serdes.lane.det_enable    = self.lane.det_enable
        serdes.lane.det_valid     = self.lane.det_valid
        serdes.lane.det_status    = self.lane.det_status
        serdes.slip               = self.slip


        return m