from nmigen import *
from nmigen.back.pysim import Simulator, Delay, Settle
from ecp5_pcie.phy_rx import PCIePhyRX
from ecp5_pcie.serdes import *
from ecp5_pcie.serdes import D, Ctrl
import random

if __name__ == "__main__":
    m = Module()
    m.submodules.rxlane = rxlane = PCIeSERDESInterface(ratio=2)
    m.submodules.aligner = lane = DomainRenamer("rx")(PCIeSERDESAligner(rxlane)) # Aligner for aligning COM symbols
    m.submodules.rx = rx = PCIePhyRX(lane)

    m.d.comb += rxlane.rx_valid.eq(0b11)

    sim = Simulator(m)
    sim.add_clock(1/125e6, domain="rx")


    # Structure of a TS:
    # COM Link Lane n_FTS Rate Ctrl ID ID ID ID ID ID ID ID ID ID
    def make_ts(link, link_valid, lane, lane_valid, n_fts, rate, ctrl, ts_id, invert):
        if ~invert & (ts_id == 1):
            id = D(10, 2)
        if invert & (ts_id == 1):
            id = D(21, 5)
        if ~invert & (ts_id == 2):
            id = D(5, 2)
        if invert & (ts_id == 2):
            id = D(26, 5)
        return [Ctrl.COM, link if link_valid else Ctrl.PAD, lane if lane_valid else Ctrl.PAD, n_fts, rate, ctrl, id, id, id, id, id, id]
    

    def make_stream(ts, shift = 0):
        if shift == 1:
            ts.insert(0, 0)
            ts.append(0)
        
        result = []

        # Turn into 18 bit long two symbol signals
        for s1, s2 in zip(ts[::2], ts[1::2]):
            result.append(Cat(Signal(9, reset=s1), Signal(9, reset=s2)))
        
        return result

    
    def send_stream(stream):
        for symbol_pair in stream:
            yield rxlane.rx_symbol.eq(symbol_pair)
            yield


    # Verify that we actually got back the right thing.
    # Wait an experimentally determined number of cycles...
    def verify(link, link_valid, lane, lane_valid, n_fts, rate, ctrl, ts_id, invert, shift, no_assert):
        yield from send_stream(make_stream(make_ts(link, link_valid, lane, lane_valid, n_fts, rate, ctrl, ts_id, invert), shift))
        yield
        yield
        yield
        yield
        yield
        yield

        if ~no_assert:
            if invert:
                assert(yield rx.ts.valid) == 0
                return

            assert (yield rx.ts.valid) == 1
            
            assert (yield rx.ts.link.valid) == link_valid
            if (yield rx.ts.link.valid):
                assert (yield rx.ts.link.number) == link

            assert (yield rx.ts.lane.valid) == lane_valid
            if (yield rx.ts.lane.valid):
                assert (yield rx.ts.lane.number) == lane

            assert (yield rx.ts.n_fts) == n_fts
            assert (yield rx.ts.rate) == rate
            assert (yield rx.ts.ctrl) == ctrl
            assert (yield rx.ts.ts_id) == ts_id - 1
    

    def process():
        # Stochastic testing, currently doesnt work for when it is shifted by 1 symbol
        #yield from verify(random.randint(0, 255), random.randint(0, 1), random.randint(0, 31), random.randint(0, 1),
        #random.randint(0, 255), random.randint(0, 255), random.randint(0, 31), random.randint(1, 2), random.randint(0, 1), 1, 1)
        #yield from verify(random.randint(0, 255), random.randint(0, 1), random.randint(0, 31), random.randint(0, 1),
        #random.randint(0, 255), random.randint(0, 255), random.randint(0, 31), random.randint(1, 2), random.randint(0, 1), 1, 1)
        for _ in range(300):
            yield from verify(random.randint(0, 255), random.randint(0, 1), random.randint(0, 31), random.randint(0, 1),
            random.randint(0, 255), random.randint(0, 255), random.randint(0, 31), random.randint(1, 2), random.randint(0, 1), 0, 0)
        yield Delay(1e-6)
        yield Settle()


    sim.add_sync_process(process, domain="rx") # or sim.add_sync_process(process), see below

    with sim.write_vcd("test.vcd", "test.gtkw", traces=sim._signal_names):
        sim.run()