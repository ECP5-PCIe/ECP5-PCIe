from nmigen import *
from nmigen.sim.pysim import Simulator, Delay, Settle
from ecp5_pcie.crc import CRC
import random

if __name__ == "__main__":
    m = Module()

    m.submodules.crc = crc = CRC(Signal(16), 0xFFFF, 0x100B, 16)

    sim = Simulator(m)
    sim.add_clock(1/125e6, domain="sync")
    
    def process():
        # Simulate a DLLP which was received from the ROCKPro64
        yield
        yield crc.reset.eq(1)
        yield
        yield crc.reset.eq(0)
        yield crc.input.eq(0x0060)
        yield
        print(hex((yield crc.output)))
        yield crc.input.eq(0x0000)
        yield
        print(hex((yield crc.output)))
        yield
        print()
        # Should output 0x92d8
        print(hex((yield ~Cat(crc.output[::-1]))))
        yield

    sim.add_sync_process(process, domain="sync")

    with sim.write_vcd("test.vcd", "test.gtkw"):
        sim.run()