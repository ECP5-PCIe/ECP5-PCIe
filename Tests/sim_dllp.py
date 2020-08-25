from nmigen import *
from nmigen.sim.pysim import Simulator, Delay, Settle
from ecp5_pcie.dllp import PCIeDLLPReceiver
from ecp5_pcie.serdes import PCIeSERDESInterface, Ctrl
import random

if __name__ == "__main__":
    m = Module()

    m.submodules.lane = lane = PCIeSERDESInterface(2)
    m.submodules.ddlpr = ddlpr = PCIeDLLPReceiver(lane)

    sim = Simulator(m)
    sim.add_clock(1/125e6, domain="rx")

    # The other two DLLPs received from the ROCKPro64
    # Refer to layouts.py for the layout of the dllp signal
    dllp_1 = [0x50, 0x08, 0x00, 0x20, 0x12, 0xd9]
    dllp_2 = [0x40, 0x08, 0x00, 0xe0, 0xf5, 0x06]

    def send_dllp(dllp):
        yield lane.rx_symbol.eq(Ctrl.SDP | (dllp[0] << 9))
        print(bin((yield ddlpr.dllp)))
        print((yield ddlpr.fifo.level))
        print()
        yield
        yield lane.rx_symbol.eq(dllp[1] | (dllp[2] << 9))
        print(bin((yield ddlpr.dllp)))
        print((yield ddlpr.fifo.level))
        print()
        yield
        yield lane.rx_symbol.eq(dllp[3] | (dllp[4] << 9))
        print(bin((yield ddlpr.dllp)))
        print((yield ddlpr.fifo.level))
        print()
        yield
        yield lane.rx_symbol.eq(dllp[5] | (Ctrl.END << 9))
        print(bin((yield ddlpr.dllp)))
        print((yield ddlpr.fifo.level))
        print()
        yield
    
    def process():
        print(bin((yield ddlpr.dllp)))
        print((yield ddlpr.fifo.level))
        print()
        yield
        yield from send_dllp(dllp_1)
        print(bin((yield ddlpr.dllp)))
        print((yield ddlpr.fifo.level))
        print()
        yield
        print(bin((yield ddlpr.dllp)))
        print((yield ddlpr.fifo.level))
        print()
        yield
        print(bin((yield ddlpr.dllp)))
        print((yield ddlpr.fifo.level))
        print()
        yield
        print(bin((yield ddlpr.dllp)))
        print((yield ddlpr.fifo.level))
        print()
        yield
        print(bin((yield ddlpr.dllp)))
        print((yield ddlpr.fifo.level))
        print()
        yield
        yield from send_dllp(dllp_2)
        print(bin((yield ddlpr.dllp)))
        print((yield ddlpr.fifo.level))
        print()
        yield
        print(bin((yield ddlpr.dllp)))
        print((yield ddlpr.fifo.level))
        print()
        yield
        print(bin((yield ddlpr.dllp)))
        print((yield ddlpr.fifo.level))
        print()
        yield
        print(bin((yield ddlpr.dllp)))
        print((yield ddlpr.fifo.level))
        print()
        yield
        print(bin((yield ddlpr.dllp)))
        print((yield ddlpr.fifo.level))
        print()
        yield

    sim.add_sync_process(process, domain="rx")

    with sim.write_vcd("test.vcd", "test.gtkw"):
        sim.run()