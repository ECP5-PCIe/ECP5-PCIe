from nmigen import *
from nmigen.back.pysim import Simulator, Delay, Settle
from ecp5_pcie.lfsr import PCIeLFSR
import random

if __name__ == "__main__":
    m = Module()

    m.submodules.lfsr = lfsr = PCIeLFSR(4, Signal(), 1)

    sim = Simulator(m)
    sim.add_clock(1/125e6, domain="rx")
    
    def process():
        for _ in range(20):
            print(hex((yield lfsr.output)))
            yield
        
        print()

        yield lfsr.reset.eq(1)
        yield
        yield lfsr.reset.eq(0)

        for _ in range(20):
            print(bin((yield lfsr.output + 0x100000000000000000)))
            yield

    sim.add_sync_process(process, domain="rx") # or sim.add_sync_process(process), see below

    with sim.write_vcd("test.vcd", "test.gtkw", traces=sim._signal_names):
        sim.run()