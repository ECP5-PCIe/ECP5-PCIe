from nmigen import *
from nmigen.build import *
import math

from .stream import StreamInterface

class RetryBuffer(Elaboratable):
    """
    """
    def __init__(self, ratio: int = 4, max_tlps: int = 4, tlp_bytes: int = 512):
        self.ratio = ratio

        self.tlp_sink = StreamInterface(8, ratio, name="TLP_Sink")
        self.tlp_source = StreamInterface(8, ratio, name="TLP_Source")

        self.max_tlps = max_tlps
        self.tlp_depth = 2 ** math.ceil(math.log2((tlp_bytes + ratio - 1) // ratio))
        self.tlp_bit_depth = math.ceil(math.log2((tlp_bytes + ratio - 1) // ratio))
        
        self.slots = [[Signal(name=f"Slot_{i}_valid"), Signal(12, name=f"Slot_{i}_ID")] for i in range(max_tlps)] # First signal indicates whether the slot is full
        self.send_tlp_id = Signal(12)
        self.send_tlp = Signal()

        self.delete_tlp_id = Signal(12)
        self.delete_tlp = Signal()

        self.store_tlp_id = Signal(12)
        self.store_tlp = Signal()

        self.free_slots = Signal(reset = 0)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        storage = Memory(width = self.ratio * 8, depth = self.tlp_depth * self.max_tlps) # TODO: Maybe there should be some kind of end mark

        read_port  = m.submodules.read_port  = storage.read_port(domain = "rx", transparent = False)
        write_port = m.submodules.write_port = storage.write_port(domain = "rx")

        for i in range(self.max_tlps):
            m.d.comb += self.free_slots.eq(self.free_slots | ~self.slots[i][0])

        read_address_base = Signal(range(self.max_tlps))
        read_address_counter = Signal(range(self.tlp_depth))
        m.d.comb += read_port.addr.eq(Cat(read_address_counter, read_address_base))
        m.d.rx += Cat(self.tlp_source.symbol).eq(read_port.data)

        tlp_source_valid = Signal(2)
        m.d.rx += tlp_source_valid.eq(tlp_source_valid << 1)
        m.d.rx += tlp_source_valid[0].eq(0)
        m.d.rx += [self.tlp_source.valid[i].eq(tlp_source_valid[-1]) for i in range(self.ratio)]
        m.d.rx += read_port.en.eq(1)

        with m.FSM(domain = "rx"):
            with m.State("Idle"):
                with m.If(self.send_tlp):
                    m.next = "Set offset"

            with m.State("Set offset"):
                offset = Signal(range(self.max_tlps))
                valid_id = Signal()

                for i in range(self.max_tlps):
                    m.d.comb += offset.eq(Mux(self.slots[i][0] & (self.slots[i][1] == self.send_tlp_id), i, offset))
                    m.d.comb += valid_id.eq(valid_id | self.slots[i][0] & (self.slots[i][1] == self.send_tlp_id))

                m.d.rx += read_address_base.eq(offset)

                with m.If(valid_id):
                    m.next = "Transmit"
                    
                with m.Else():
                    m.next = "Idle"
            
            with m.State("Transmit"):
                m.d.rx += [
                    read_address_counter.eq(read_address_counter + 1),
                    tlp_source_valid[0].eq(1),
                ]

                with m.If(read_address_counter == self.tlp_depth - 1):
                    m.d.rx += read_address_counter.eq(0)
                    m.d.rx += self.send_tlp.eq(0)
                    m.next = "Idle"
        

        with m.If(self.delete_tlp):
            for i in range(self.max_tlps):
                with m.If(self.slots[i][0] & (self.delete_tlp_id == self.slots[i][1])):
                    m.d.rx += self.slots[i][0].eq(0)
                    m.d.rx += self.delete_tlp.eq(0)


        write_address_base = Signal(range(self.max_tlps))
        write_address_counter = Signal(range(self.tlp_depth))
        m.d.comb += write_port.addr.eq(Cat(write_address_counter, write_address_base))
        m.d.rx += write_port.data.eq(Cat(self.tlp_sink.symbol))

        m.d.rx += self.tlp_sink.ready.eq(0)
        m.d.rx += write_port.en.eq(0)

        with m.FSM(domain = "rx"):
            with m.State("Idle"):
                with m.If(self.store_tlp):
                    m.next = "Set offset"

            with m.State("Set offset"):
                offset = Signal(range(self.max_tlps))

                for i in range(self.max_tlps):
                    m.d.comb += offset.eq(Mux(~self.slots[i][0], i, offset))

                for i in range(self.max_tlps):
                    with m.If(offset == i):
                        m.d.rx += self.slots[i][0].eq(1)
                        m.d.rx += self.slots[i][1].eq(self.store_tlp_id)

                m.d.rx += write_address_base.eq(offset)
                m.d.rx += self.tlp_sink.ready.eq(1)

                m.next = "Receive"
            
            with m.State("Receive"):
                m.d.rx += self.tlp_sink.ready.eq(1)

                with m.If(self.tlp_sink.all_valid):
                    m.d.rx += write_address_counter.eq(write_address_counter + 1)
                    m.d.rx += write_port.en.eq(1)

                with m.If(write_address_counter == self.tlp_depth - 1):
                    m.d.rx += self.tlp_sink.ready.eq(0)
                    m.d.rx += write_address_counter.eq(0)
                    m.d.rx += self.store_tlp.eq(0)
                    m.next = "Idle"


        return m