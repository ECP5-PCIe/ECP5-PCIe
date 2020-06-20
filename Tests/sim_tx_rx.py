from nmigen import *
from nmigen.back.pysim import Simulator, Delay, Settle
from ecp5_pcie.phy_rx import PCIePhyRX
from ecp5_pcie.phy_tx import PCIePhyTX
from ecp5_pcie.serdes import *

if __name__ == "__main__":
    m = Module()
    m.submodules.rxlane = rxlane = PCIeSERDESInterface(ratio=2)
    m.submodules.txlane = txlane = PCIeSERDESInterface(ratio=2)
    m.submodules.aligner = lane = DomainRenamer("rx")(PCIeSERDESAligner(rxlane)) # Aligner for aligning COM symbols
    m.submodules.rx = rx = PCIePhyRX(lane)
    m.submodules.tx = tx = PCIePhyTX(txlane)

    m.d.comb += rxlane.rx_symbol.eq(txlane.tx_symbol)
    m.d.comb += rxlane.rx_valid.eq(0b11)

    m.d.tx += tx.ts.valid.eq(1)
    m.d.tx += tx.ts.link.valid.eq(0)
    m.d.tx += tx.ts.lane.valid.eq(1)
    m.d.tx += tx.ts.n_fts.eq(123)
    m.d.tx += tx.ts.rate.gen1.eq(1)

    sim = Simulator(m)
    sim.add_clock(1/125e6, domain="rx")
    sim.add_clock(1/125e6, domain="tx")


    def process():
        yield Delay(1e-6)
        yield Settle()


    sim.add_process(process)

    with sim.write_vcd("test.vcd", "test.gtkw", traces=sim._signal_names):
        sim.run()