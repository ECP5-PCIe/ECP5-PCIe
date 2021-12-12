from amaranth import *
from amaranth.build import *
from amaranth.sim.pysim import Simulator, Delay, Settle
from ecp5_pcie.crc import SingleCRC
from amaranth_boards.versa_ecp5_5g import VersaECP55GPlatform
import random

if __name__ == "__main__":
    m = Module()

    m.submodules.crc = crc = SingleCRC(Signal(32), 0xFFFF, 0x100B, 16)

    input = Signal(32)
    m.d.sync += crc.input.eq(input)

    sim = Simulator(m)
    sim.add_clock(1/125e6, domain="sync")# For NextPNR, set the maximum clock frequency such that errors are given

    
    def process():
        # Simulate a DLLP which was received from the ROCKPro64
        yield
        yield input.eq(Cat(Const(0x50, 8), Const(0x08, 8), Const(0x00, 8), Const(0x20, 8)))
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

    exit()

    class TestCRC(Elaboratable):
        def elaborate(self, platform: Platform) -> Module:
            m = Module()

            clk = ClockDomain()

            leds = [platform.request("led", i).o for i in range(8)]
            switches = [platform.request("switch", i) for i in range(8)]

            m.d.comb += clk.clk.eq(switches[0])
            platform.add_clock_constraint(clk.clk, 300e6)
            m.domains.clk = clk

            #m.submodules.crc = crc = DomainRenamer("clk")(CRC(Cat(switches, [switch for switch in switches]) ^ Cat(~Cat(leds), leds[4:8], leds[0:4]), 0xFFFF, 0x139B82546998246B, 16))
            #m.d.clk += Cat(leds).eq(crc.output)

            return m

    import os
    os.environ["AMARANTH_verbose"] = "Yes"

    VersaECP55GPlatform().build(TestCRC(), do_program=False)