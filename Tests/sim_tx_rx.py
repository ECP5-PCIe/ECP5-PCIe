from amaranth import *
from amaranth.back.pysim import Simulator, Delay, Settle
from ecp5_pcie.phy_rx import PCIePhyRX
from ecp5_pcie.phy_tx import PCIePhyTX
from ecp5_pcie.serdes import *
import random

if __name__ == "__main__":
    m = Module()
    m.submodules.rxlane = rxlane = PCIeSERDESInterface(ratio=2)
    m.submodules.txlane = txlane = PCIeSERDESInterface(ratio=2)
    m.submodules.aligner = aligned_rxlane = DomainRenamer("rx")(PCIeSERDESAligner(rxlane)) # Aligner for aligning COM symbols
    m.submodules.rx = rx = PCIePhyRX(aligned_rxlane)
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


    # Checks if the sent and the received TSs are the same.
    def verify(link, link_valid, lane, lane_valid, n_fts, rate, ctrl, ts_id):
        if link_valid:
            yield tx.ts.link.number.eq(link)
        yield tx.ts.link.valid .eq(link_valid)
        if lane_valid:
            yield tx.ts.lane.number.eq(lane)
        yield tx.ts.lane.valid .eq(lane_valid)
        yield tx.ts.n_fts      .eq(n_fts)
        yield tx.ts.rate       .eq(rate)
        yield tx.ts.ctrl       .eq(ctrl)
        yield tx.ts.ts_id      .eq(ts_id - 1)
        yield tx.ts.valid      .eq(1)

        for _ in range(16):
            yield

        tx_ts = yield tx.ts
        rx_ts = yield rx.ts

        assert tx_ts == rx_ts
    

    def process():
        # Stochastic testing
        for _ in range(300):
            yield from verify(random.randint(0, 255), random.randint(0, 1), random.randint(0, 31), random.randint(0, 1),
            random.randint(0, 255), random.randint(0, 255), random.randint(0, 31), random.randint(1, 2))
        yield Delay(1e-6)
        yield Settle()


    sim.add_sync_process(process, domain="rx") # or sim.add_sync_process(process), see below

    with sim.write_vcd("test.vcd", "test.gtkw", traces=sim._signal_names):
        sim.run()