from ecp5_pcie.memory import RetryBuffer
from nmigen import *
from nmigen.sim import Simulator, Delay, Settle



if __name__ == "__main__":
    test_bytes = [i for i in range(16)] * 4

    test_bytes = test_bytes

    m = Module()

    m.submodules.buffer = buffer = RetryBuffer(tlp_bytes=32)

    val = Signal(8, reset=13)
    with m.If(buffer.tlp_sink.ready):
        m.d.comb += buffer.tlp_sink.symbol[0].eq(val)
        m.d.comb += Cat(buffer.tlp_sink.valid).eq(0b1111)
        m.d.rx += val.eq(val + 1)

    sim = Simulator(m)

    sim.add_clock(1E-9, domain="rx")

    def process():
        yield buffer.store_tlp.eq(1)
        yield buffer.store_tlp_id.eq(123)
        sm1 = 1
        for i in range(len(test_bytes) * 3):
            store = (yield buffer.store_tlp)

            if not store and not sm1:
                yield buffer.send_tlp.eq(1)
                yield buffer.send_tlp_id.eq(123)

            sm1 = store

            if i > len(test_bytes) * 2:
                yield buffer.delete_tlp.eq(1)
                yield buffer.delete_tlp_id.eq(123)

            yield

    sim.add_sync_process(process, domain="rx")

    with sim.write_vcd("test_memory.vcd", "test_memory.gtkw"):
        sim.run()