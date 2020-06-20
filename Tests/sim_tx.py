from nmigen import *
from nmigen.back.pysim import Simulator, Delay, Settle
from ecp5_pcie.phy_rx import PCIePhyRX
from ecp5_pcie.phy_tx import PCIePhyTX
from ecp5_pcie.serdes import *
from ecp5_pcie.serdes import D, Ctrl
import random

if __name__ == "__main__":
    m = Module()
    m.submodules.txlane = txlane = PCIeSERDESInterface(ratio=2)
    m.submodules.tx = tx = PCIePhyTX(txlane)

    sim = Simulator(m)
    sim.add_clock(1/125e6, domain="tx")


    # Structure of a TS:
    # COM Link Lane n_FTS Rate Ctrl ID ID ID ID ID ID ID ID ID ID
    def make_ts(link, link_valid, lane, lane_valid, n_fts, rate, ctrl, ts_id):
        if ts_id == 1:
            id = D(10, 2)
        if ts_id == 2:
            id = D(5, 2)
        return [Ctrl.COM, link if link_valid else Ctrl.PAD, lane if lane_valid else Ctrl.PAD, n_fts, rate, ctrl, id, id, id, id, id, id]
    

    def make_stream(ts, shift = 0):
        if shift == 1:
            ts.insert(0, 0)
            ts.append(0)
        
        result = []

        # Turn into 18 bit long two symbol signals
        for s1, s2 in zip(ts[::2], ts[1::2]):
            result.append((s2 << 9) | s1) #Cat(Signal(9, reset=s1), Signal(9, reset=s2)))
        
        yield
        return result


    # Send TS and then check if the right data is being sent, TBD
    def verify(link, link_valid, lane, lane_valid, n_fts, rate, ctrl, ts_id):
        yield tx.ts.link.number.eq(link)
        yield tx.ts.link.valid .eq(link_valid)
        yield tx.ts.lane.number.eq(lane)
        yield tx.ts.lane.valid .eq(lane_valid)
        yield tx.ts.n_fts      .eq(n_fts)
        yield tx.ts.rate       .eq(rate)
        yield tx.ts.ctrl       .eq(ctrl)
        yield tx.ts.ts_id      .eq(ts_id - 1)
        yield tx.ts.valid      .eq(1)

        comparison = yield from make_stream(make_ts(link, link_valid, lane, lane_valid, n_fts, rate, ctrl, ts_id))

        sent = []
        yield
        sent.append((yield txlane.tx_symbol))
        yield
        sent.append((yield txlane.tx_symbol))
        yield
        sent.append((yield txlane.tx_symbol))
        yield
        sent.append((yield txlane.tx_symbol))
        yield
        sent.append((yield txlane.tx_symbol))
        yield
        sent.append((yield txlane.tx_symbol))
        yield

        assert sent == comparison
    

    def process():
        # Stochastic testing
        for _ in range(300):
            yield from verify(random.randint(0, 255), random.randint(0, 1), random.randint(0, 31), random.randint(0, 1),
            random.randint(0, 255), random.randint(0, 255), random.randint(0, 31), random.randint(1, 2))
        yield Delay(1e-6)
        yield Settle()


    sim.add_sync_process(process, domain="tx") # or sim.add_sync_process(process), see below

    with sim.write_vcd("test.vcd", "test.gtkw", traces=sim._signal_names):
        sim.run()