from amaranth import *
from amaranth.sim.pysim import Simulator, Delay, Settle
from ecp5_pcie.dllp import PCIeDLLPReceiver
from ecp5_pcie.stream import StreamInterface
from ecp5_pcie.serdes import PCIeSERDESInterface, Ctrl
import random

if __name__ == "__main__":
    m = Module()

    stream = StreamInterface(9, 4)
    m.submodules.dllpr = dllpr = PCIeDLLPReceiver(stream)

    sim = Simulator(m)
    sim.add_clock(1/125e6, domain="rx")

    # The other two DLLPs received from the ROCKPro64
    # Refer to layouts.py for the layout of the dllp signal
    dllp_1 = [0x50, 0x08, 0x00, 0x20, 0x12, 0xd9]
    dllp_2 = [0x40, 0x08, 0x00, 0xe0, 0xf5, 0x06]

    symbol = [Signal(9), Signal(9), Signal(9), Signal(9)]

    print(symbol)

    for i in range(4):
        m.d.rx += stream.symbol[i].eq(symbol[i])

    def send_dllp(dllp):
        yield stream.symbol[0].eq(Ctrl.SDP)
        yield stream.symbol[1].eq(dllp[0])
        yield stream.symbol[2].eq(dllp[1])
        yield stream.symbol[3].eq(dllp[2])
        for i in range(4):
            yield stream.valid[i].eq(1)
        print(hex((yield dllpr.dllp)))
        print(bin((yield stream.symbol[0])))
        print(bin((yield stream.symbol[1])))
        print(bin((yield stream.symbol[2])))
        print(bin((yield stream.symbol[3])))
        print(bin((yield stream.valid[3])))
        print()
        yield
        yield stream.symbol[0].eq(dllp[3])
        yield stream.symbol[1].eq(dllp[4])
        yield stream.symbol[2].eq(dllp[5])
        yield stream.symbol[3].eq(Ctrl.END)
        print(hex((yield dllpr.dllp)))
        print(bin((yield stream.symbol[0])))
        print(bin((yield stream.symbol[1])))
        print(bin((yield stream.symbol[2])))
        print(bin((yield stream.symbol[3])))
        print(bin((yield stream.valid[3])))
        print()
        print()
        print()
        yield
    
    def process():
        print(bin((yield dllpr.dllp)))
        print()
        yield
        yield from send_dllp(dllp_1)
        print(bin((yield dllpr.dllp)))
        print()
        yield
        print(bin((yield dllpr.dllp)))
        print()
        yield
        print(bin((yield dllpr.dllp)))
        print()
        yield
        print(bin((yield dllpr.dllp)))
        print()
        yield
        print(bin((yield dllpr.dllp)))
        print()
        yield
        yield from send_dllp(dllp_2)
        print(bin((yield dllpr.dllp)))
        print()
        yield
        print(bin((yield dllpr.dllp)))
        print()
        yield
        print(bin((yield dllpr.dllp)))
        print()
        yield
        print(bin((yield dllpr.dllp)))
        print()
        yield
        print(bin((yield dllpr.dllp)))
        print()
        yield

        yield from send_dllp(dllp_1)
        yield from send_dllp(dllp_2)
        yield from send_dllp(dllp_1)
        yield from send_dllp(dllp_2)
        print(bin((yield dllpr.dllp)))
        print()
        yield
        print(bin((yield dllpr.dllp)))
        print()
        yield
        print(bin((yield dllpr.dllp)))
        print()
        yield
        print(bin((yield dllpr.dllp)))
        print()
        yield
        print(bin((yield dllpr.dllp)))
        print()
        yield

        print()
        print()
        print()
        print()

        yield dllpr.fifo.r_en.eq(1)
        print(bin((yield dllpr.fifo.r_data)))
        print()
        yield
        print(bin((yield dllpr.fifo.r_data)))
        print()
        yield
        print(bin((yield dllpr.fifo.r_data)))
        print()
        yield
        print(bin((yield dllpr.fifo.r_data)))
        yield dllpr.fifo.r_en.eq(0)
        print()
        yield
        print(bin((yield dllpr.fifo.r_data)))
        print()
        yield
        print(bin((yield dllpr.fifo.r_data)))
        yield dllpr.fifo.r_en.eq(1)
        print()
        yield
        print(bin((yield dllpr.fifo.r_data)))
        print()
        yield
        print(bin((yield dllpr.fifo.r_data)))
        print()
        yield
        print(bin((yield dllpr.fifo.r_data)))
        print()
        yield
        print(bin((yield dllpr.fifo.r_data)))
        print()
        yield

    sim.add_sync_process(process, domain="rx")

    with sim.write_vcd("test.vcd", "test.gtkw"):
        sim.run()