from nmigen import *
from nmigen.sim.pysim import Simulator, Delay, Settle
from ecp5_pcie.dllp import PCIeDLLPTransmitter
from ecp5_pcie.serdes import PCIeSERDESInterface, Ctrl
import random

if __name__ == "__main__":
    m = Module()

    output = Signal(18)
    m.submodules.dllpt = dllpt = PCIeDLLPTransmitter(output)

    m.d.comb += dllpt.send.eq(1)

    sim = Simulator(m)
    sim.add_clock(1/125e6, domain="rx")

    # The other two DLLPs received from the ROCKPro64
    # Refer to layouts.py for the layout of the dllp signal
    dllp_1 = 0b1000011100000001000000000100
    dllp_2 = 0b1000000100000001000000000101
    
    def process():
        yield dllpt.dllp.eq(dllp_1)
        print(hex((yield output[0:9])), end="\t")
        print(hex((yield output[9:18])))
        #print(hex((yield dllpt.symbols[0])), end="\t")
        #print(hex((yield dllpt.symbols[1])))
        #print(hex((yield dllpt.crc_out)))
        print()
        yield
        #yield dllpt.dllp.valid.eq(0)
        for _ in range(20):
            print(hex((yield output[0:9])), end="\t")
            print(hex((yield output[9:18])))
            #print(hex((yield dllpt.symbols[0])), end="\t")
            #print(hex((yield dllpt.symbols[1])))
            #print(hex((yield dllpt.crc_out)))
            print()
            yield

    sim.add_sync_process(process, domain="rx")

    with sim.write_vcd("test.vcd", "test.gtkw"):
        sim.run()