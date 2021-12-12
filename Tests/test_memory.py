from ecp5_pcie.memory import TLPBuffer
from amaranth import *
from amaranth.sim import Simulator, Delay, Settle



if __name__ == "__main__":
    m = Module()

    m.submodules.buffer = buffer = TLPBuffer(tlp_bytes=64)

    time = Signal(32)

    m.d.rx += time.eq(time + 1)

    end_val = Signal(8)

    val = Signal(8)
    with m.If(buffer.tlp_sink.ready):
        m.d.comb += buffer.tlp_sink.symbol[0].eq(val)
        m.d.comb += Cat(buffer.tlp_sink.valid).eq(Mux(val <= end_val, 0b1111, 0b0000))
        m.d.rx += val.eq(val + 1)
    
    m.d.rx += buffer.tlp_source.ready.eq(1)

    def store_tlp(start, end, id):
        return [val.eq(start),
            end_val.eq(end),
            buffer.store_tlp.eq(1),
            buffer.store_tlp_id.eq(id)]


    sim = Simulator(m)

    sim.add_clock(1E-9, domain="rx")

    def process():
        sm1 = 1
        for i in range(1000):
            if i == 0:
                for statement in store_tlp(5, 8, 0xAB):
                    yield statement
                print("Store 1")

            # This shouldn't overwrite an existing TLP
            if i == 50:
                for statement in store_tlp(9, 17, 0xAB):
                    yield statement
                print("Store 2")

            if i == 100:
                for statement in store_tlp(0xAA, 0xAA + 31, 0xCA):
                    yield statement
                print("Store 3")

            if i == 150:
                for statement in store_tlp(0xF0, 0xF1, 0x1EF):
                    yield statement
                print("Store 4")

            if i == 300:
                yield buffer.send_tlp.eq(1)
                yield buffer.send_tlp_id.eq(0xCA)

            if i == 400:
                yield buffer.send_tlp.eq(1)
                yield buffer.send_tlp_id.eq(0xAB)

            if i == 500:
                yield buffer.send_tlp.eq(1)
                yield buffer.send_tlp_id.eq(0xCA)

            if i == 600:
                yield buffer.delete_tlp.eq(1)
                yield buffer.delete_tlp_id.eq(0xCA)

            if i == 700:
                yield buffer.send_tlp.eq(1)
                yield buffer.send_tlp_id.eq(0xCA)

            if i == 800:
                yield buffer.send_tlp.eq(1)
                yield buffer.send_tlp_id.eq(0x1EF)

            
            if (yield buffer.tlp_source.valid[0]):
                print(i, hex((yield buffer.send_tlp_id))[2:], hex((yield buffer.tlp_source.symbol[0]))[2:])



            #store = (yield buffer.store_tlp)
            #
            #if not store and not sm1:
            #    yield buffer.send_tlp.eq(1)
            #    yield buffer.send_tlp_id.eq(123)
            #
            #sm1 = store

            #if i == 700:
            #    yield buffer.delete_tlp.eq(1)
            #    yield buffer.delete_tlp_id.eq(123)

            yield

    sim.add_sync_process(process, domain="rx")

    with sim.write_vcd("test_memory.vcd", "test_memory.gtkw"):
        sim.run()