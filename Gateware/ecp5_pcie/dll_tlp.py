from amaranth import *
from amaranth.build import *
from amaranth.lib.fifo import SyncFIFOBuffered

from .layouts import dllp_layout
from .serdes import K, D, Ctrl
from .crc import LCRC
from .stream import StreamInterface
from .dll import PCIeDLL
from .memory import TLPBuffer

class PCIeDLLTLPTransmitter(Elaboratable):
    """
    """
    def __init__(self, dll: PCIeDLL, ratio: int = 4):
        self.tlp_sink = StreamInterface(8, ratio, name="TLP_Sink")
        self.dllp_source = StreamInterface(9, ratio, name="DLLP_Source") # TODO: Maybe connect these in elaborate instead of where this class is instantiated

        self.dll = dll

        self.send = Signal()
        self.started_sending = Signal()
        self.accepts_tlps = Signal()
        self.nullify = Signal() # if this is 1 towards the end of the TLP, the TLP will be nullified (set to 1 in rx domain, will be set to 0 by this module)
        assert len(self.dllp_source.symbol) == 4
        assert len(self.tlp_sink.symbol) == 4
        self.ratio = len(self.dllp_source.symbol)

        self.clocks_per_ms = 62500

        # See page 142 in PCIe 1.1
        self.next_transmit_seq = Signal(12, reset=0x000) # TLP sequence number
        self.ackd_seq = Signal(12, reset=0xFFF) # Last acknowledged TLP
        self.replay_num = Signal(2, reset=0b00) # Number of times the retry buffer has been re-transmitted
        self.replay_timeout = 462 # TODO: is 462 right number? See page 148 Table 3-4 PCIe 1.1
        self.replay_timer = Signal(range(self.replay_timeout), reset=0)  # Time since last TLP has finished transmitting, hold if LTSSM in recovery
        self.replay_timer_running = Signal()


        #self.tlp_data = Signal(4 * 8)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        ratio = self.ratio
        assert ratio == 4

        # Maybe these should be moved into PCIeDLLTLP class since it also involves RX a bit
        m.submodules.buffer = buffer = TLPBuffer(ratio = ratio, max_tlps = 2 ** len(self.replay_num))
        m.submodules.unacknowledged_tlp_fifo = unacknowledged_tlp_fifo = SyncFIFOBuffered(width = 12, depth = 4)

        source_from_buffer = Signal()
        sink_ready = Signal()
        m.d.comb += buffer.tlp_source.ready.eq(sink_ready & source_from_buffer)
        m.d.comb += self.tlp_sink.ready.eq(sink_ready & ~source_from_buffer)
        sink_valid = Mux(source_from_buffer, buffer.tlp_source.all_valid, self.tlp_sink.all_valid)
        sink_symbol = [Mux(source_from_buffer, buffer.tlp_source.symbol[i], self.tlp_sink.symbol[i]) for i in range(ratio)]

        self.tlp_sink.connect(buffer.tlp_sink, m.d.comb)

        with m.If(self.dll.up):
            m.d.comb += buffer.store_tlp.eq(1) # TODO: Is this a good idea?
            m.d.rx += buffer.store_tlp_id.eq(self.next_transmit_seq)
            m.d.rx += buffer.send_tlp_id.eq(unacknowledged_tlp_fifo.r_data)
            m.d.rx += unacknowledged_tlp_fifo.r_en.eq(0)
        
        with m.Else():
            m.d.rx += self.next_transmit_seq.eq(self.next_transmit_seq.reset)
            m.d.rx += self.ackd_seq.eq(self.ackd_seq.reset)
            m.d.rx += self.replay_num.eq(self.replay_num.reset)
        
        m.d.rx += self.accepts_tlps.eq((self.next_transmit_seq - self.ackd_seq) >= 2048) # mod 4096 is already applied since the signal is 12 bits long

        with m.If(self.replay_timer_running):
            m.d.rx += self.replay_timer.eq(self.replay_timer + 1)

        #with m.FSM(domain = "rx"):
        #    with m.State("Idle"):
        #        m.d.rx += source_from_buffer.eq(0)
#
        #        with m.If(self.replay_timer >= self.replay_timeout):
        #            m.next = "Replay"
        #        
        #        with m.If(NAK received):
        #            m.next = "Replay"
#
        #    with m.State("Replay"):
        #        m.d.rx += source_from_buffer.eq(1)
#
        #        with m.If(buffer.slots_empty):
        #            m.d.rx += source_from_buffer.eq(0)
        #            m.next = "Idle"
        #
        #If ACK received:
        #Delete entry from retry buffer and advance unacknowledged_tlp_fifo
#
        #with m.If(buffer.slots_full):
        #    YEET!
        
        reset_crc = Signal(reset = 1)
        # TODO Warning: Endianness
        crc_input = Signal(32)
        m.submodules.lcrc = lcrc = LCRC(crc_input, reset_crc)

        last_valid = Signal()
        m.d.rx += last_valid.eq(sink_valid)
        last_last_valid = Signal() # TODO: Maybe there is a better way
        m.d.rx += last_last_valid.eq(last_valid)
        last_last_last_valid = Signal() # TODO: Maybe there is a better way 😿 like a longer signal which gets shifted for example
        m.d.rx += last_last_last_valid.eq(last_last_valid)


        tlp_bytes = Signal(8 * self.ratio)
        tlp_bytes_before = Signal(8 * self.ratio)

        with m.If(sink_valid):
            m.d.comb += Cat(tlp_bytes[0 : 8 * ratio]).eq(Cat(sink_symbol)) # TODO: Endianness correct?
            m.d.rx += Cat(tlp_bytes_before[0 : 8 * ratio]).eq(Cat(sink_symbol)) # TODO: Endianness correct?

        with m.Else():
            with m.If(self.nullify):
                m.d.comb += Cat(tlp_bytes[0 : 8 * ratio]).eq(~lcrc.output) # ~~x = x
                m.d.rx += Cat(tlp_bytes_before[0 : 8 * ratio]).eq(~lcrc.output)
                m.d.comb += buffer.delete_tlp.eq(1)
                m.d.comb += buffer.delete_tlp_id.eq(self.next_transmit_seq)

            with m.Else():
                m.d.comb += Cat(tlp_bytes[0 : 8 * ratio]).eq(lcrc.output) # TODO: Endianness correct?
                m.d.rx += Cat(tlp_bytes_before[0 : 8 * ratio]).eq(lcrc.output) # TODO: Endianness correct?


        #m.d.rx += Cat(tlp_bytes[8 * ratio : 2 * 8 * ratio]).eq(Cat(tlp_bytes[0 : 8 * ratio]))

        even_more_delay = [Signal(9) for i in range(4)]

        m.d.rx += unacknowledged_tlp_fifo.w_en.eq(0)

        m.d.comb += sink_ready.eq(0) # TODO: maybe move to rx?

        delayed_symbol = Signal(32)
        m.d.rx += delayed_symbol.eq(Cat(sink_symbol))
        m.d.comb += crc_input.eq(delayed_symbol)

        for i in range(4):
            m.d.rx += self.dllp_source.valid[i].eq(0)


        with m.If(self.dllp_source.ready & unacknowledged_tlp_fifo.w_rdy):
            m.d.comb += sink_ready.eq(1) # TODO: maybe move to rx?
            with m.FSM(name = "TLP_transmit_FSM", domain = "rx"):
                with m.State("Idle"):
                    with m.If(~last_valid & sink_valid):
                        m.d.comb += reset_crc.eq(0)
                        m.d.comb += crc_input.eq(Cat(self.next_transmit_seq[8 : 12], Const(0, shape = 4), self.next_transmit_seq[0 : 8]))
                        m.d.rx += even_more_delay[0].eq(Ctrl.STP)
                        m.d.rx += even_more_delay[1].eq(self.next_transmit_seq[8 : 12])
                        m.d.rx += even_more_delay[2].eq(self.next_transmit_seq[0 : 8])
                        m.d.rx += even_more_delay[3].eq(tlp_bytes[8 * 0 : 8 * 1])
                        m.next = "Transmit"

                with m.State("Transmit"):
                    with m.If(last_valid & sink_valid):
                        m.d.comb += reset_crc.eq(0)
                        m.d.rx += even_more_delay[0].eq(tlp_bytes_before[8 * 1 : 8 * 2])
                        m.d.rx += even_more_delay[1].eq(tlp_bytes_before[8 * 2 : 8 * 3])
                        m.d.rx += even_more_delay[2].eq(tlp_bytes_before[8 * 3 : 8 * 4])
                        m.d.rx += even_more_delay[3].eq(tlp_bytes[8 * 0 : 8 * 1])
                        for i in range(4):
                            m.d.rx += self.dllp_source.symbol[i].eq(even_more_delay[i])
                        for i in range(4):
                            m.d.rx += self.dllp_source.valid[i].eq(1)

                    with m.Elif(~sink_valid):
                        m.d.comb += reset_crc.eq(0)
                        m.d.comb += sink_ready.eq(0) # TODO: maybe move to rx?
                        m.d.rx += even_more_delay[0].eq(tlp_bytes_before[8 * 1 : 8 * 2])
                        m.d.rx += even_more_delay[1].eq(tlp_bytes_before[8 * 2 : 8 * 3])
                        m.d.rx += even_more_delay[2].eq(tlp_bytes_before[8 * 3 : 8 * 4])
                        for i in range(4):
                            m.d.rx += self.dllp_source.symbol[i].eq(even_more_delay[i])
                        for i in range(4):
                            m.d.rx += self.dllp_source.valid[i].eq(1)
                        m.next = "Post-1"

                with m.State("Post-1"):
                    m.d.rx += self.dllp_source.symbol[3].eq(tlp_bytes[8 * 0 : 8 * 1])

                    for i in range(3):
                        m.d.rx += self.dllp_source.symbol[i].eq(even_more_delay[i])

                    for i in range(4):
                        m.d.rx += self.dllp_source.valid[i].eq(1)

                    m.next = "Post-2"
                
                with m.State("Post-2"):
                    m.d.comb += sink_ready.eq(0) # TODO: maybe move to rx?
                    m.d.rx += self.dllp_source.symbol[0].eq(tlp_bytes_before[8 * 1 : 8 * 2])
                    m.d.rx += self.dllp_source.symbol[1].eq(tlp_bytes_before[8 * 2 : 8 * 3])
                    m.d.rx += self.dllp_source.symbol[2].eq(tlp_bytes_before[8 * 3 : 8 * 4])

                    with m.If(self.nullify):
                        m.d.rx += self.dllp_source.symbol[3].eq(Ctrl.EDB)
                        m.d.rx += self.nullify.eq(0)

                    with m.Else():
                        m.d.rx += self.dllp_source.symbol[3].eq(Ctrl.END)
                        m.d.rx += unacknowledged_tlp_fifo.w_data.eq(self.next_transmit_seq)
                        m.d.rx += unacknowledged_tlp_fifo.w_en.eq(1)
                        m.d.rx += self.next_transmit_seq.eq(self.next_transmit_seq + 1)
                    
                    m.d.rx += self.replay_timer_running.eq(1) # TODO: Maybe this should be in the Else block above

                    for i in range(4):
                        m.d.rx += self.dllp_source.valid[i].eq(1)

                    m.next = "Idle"




        # TODO: This could be a FSM
        #with m.If(self.dllp_source.ready & unacknowledged_tlp_fifo.w_rdy):
        #    m.d.comb += sink_ready.eq(1) # TODO: maybe move to rx?
#
        #    with m.If(~last_valid & sink_valid):
        #        m.d.comb += reset_crc.eq(0)
        #        m.d.comb += crc_input.eq(Cat(self.next_transmit_seq[8 : 12], Const(0, shape = 4), self.next_transmit_seq[0 : 8]))
        #        m.d.rx += even_more_delay[0].eq(Ctrl.STP)
        #        m.d.rx += even_more_delay[1].eq(self.next_transmit_seq[8 : 12])
        #        m.d.rx += even_more_delay[2].eq(self.next_transmit_seq[0 : 8])
        #        m.d.rx += even_more_delay[3].eq(tlp_bytes[8 * 0 : 8 * 1])
        #        #for i in range(4):
        #        #    m.d.rx += self.dllp_source.symbol[i].eq(even_more_delay[i])
#
        #    with m.Elif(last_valid & sink_valid):
        #        m.d.comb += reset_crc.eq(0)
        #        m.d.rx += even_more_delay[0].eq(tlp_bytes_before[8 * 1 : 8 * 2])
        #        m.d.rx += even_more_delay[1].eq(tlp_bytes_before[8 * 2 : 8 * 3])
        #        m.d.rx += even_more_delay[2].eq(tlp_bytes_before[8 * 3 : 8 * 4])
        #        m.d.rx += even_more_delay[3].eq(tlp_bytes[8 * 0 : 8 * 1])
        #        for i in range(4):
        #            m.d.rx += self.dllp_source.symbol[i].eq(even_more_delay[i])
        #        for i in range(4):
        #            m.d.rx += self.dllp_source.valid[i].eq(1)
#
        #    with m.Elif(last_valid & ~sink_valid): # Maybe this can be done better and replaced by the two if blocks above
        #        m.d.comb += reset_crc.eq(0)
        #        m.d.comb += sink_ready.eq(0) # TODO: maybe move to rx?
        #        m.d.rx += even_more_delay[0].eq(tlp_bytes_before[8 * 1 : 8 * 2])
        #        m.d.rx += even_more_delay[1].eq(tlp_bytes_before[8 * 2 : 8 * 3])
        #        m.d.rx += even_more_delay[2].eq(tlp_bytes_before[8 * 3 : 8 * 4])
        #        for i in range(4):
        #            m.d.rx += self.dllp_source.symbol[i].eq(even_more_delay[i])
        #        for i in range(4):
        #            m.d.rx += self.dllp_source.valid[i].eq(1)
#
        #    with m.Elif(last_last_valid & ~sink_valid):
        #        m.d.rx += self.dllp_source.symbol[3].eq(tlp_bytes[8 * 0 : 8 * 1])
#
        #        for i in range(3):
        #            m.d.rx += self.dllp_source.symbol[i].eq(even_more_delay[i])
#
        #        for i in range(4):
        #            m.d.rx += self.dllp_source.valid[i].eq(1)
#
        #    with m.Elif(last_last_last_valid & ~sink_valid):
        #        m.d.comb += sink_ready.eq(0) # TODO: maybe move to rx?
        #        m.d.rx += self.dllp_source.symbol[0].eq(tlp_bytes_before[8 * 1 : 8 * 2])
        #        m.d.rx += self.dllp_source.symbol[1].eq(tlp_bytes_before[8 * 2 : 8 * 3])
        #        m.d.rx += self.dllp_source.symbol[2].eq(tlp_bytes_before[8 * 3 : 8 * 4])
#
        #        with m.If(self.nullify):
        #            m.d.rx += self.dllp_source.symbol[3].eq(Ctrl.EDB)
        #            m.d.rx += self.nullify.eq(0)
#
        #        with m.Else():
        #            m.d.rx += self.dllp_source.symbol[3].eq(Ctrl.END)
        #            m.d.rx += unacknowledged_tlp_fifo.w_data.eq(self.next_transmit_seq)
        #            m.d.rx += unacknowledged_tlp_fifo.w_en.eq(1)
        #            m.d.rx += self.next_transmit_seq.eq(self.next_transmit_seq + 1)
        #        
        #        m.d.rx += self.replay_timer_running.eq(1) # TODO: Maybe this should be in the Else block above
#
        #        for i in range(4):
        #            m.d.rx += self.dllp_source.valid[i].eq(1)


        return m

class PCIeDLLTLPReceiver(Elaboratable):
    """
    """
    def __init__(self, dll: PCIeDLL, ratio: int = 4):
        self.tlp_source = StreamInterface(8, ratio, name="TLP_Sink")
        self.dllp_sink = StreamInterface(9, ratio, name="DLLP_Source") # TODO: Maybe connect these in elaborate instead of where this class is instantiated

        self.dll = dll
        
        assert len(self.dllp_sink.symbol) == 4
        assert len(self.tlp_source.symbol) == 4
        self.ratio = len(self.dllp_sink.symbol)

        self.clocks_per_ms = 62500

        # See page 142 in PCIe 1.1
        self.next_receive_seq = Signal(12, reset=0x000) # Expected TLP sequence number
        self.nak_scheduled = Signal(reset = 0)
        self.ack_nak_latency_timer = Signal(range(self.replay_timeout), reset=0) # Time since an Ack or Nak DLLP was scheduled for transmission


        #self.tlp_data = Signal(4 * 8)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        ratio = self.ratio
        assert ratio == 4

        # Maybe these should be moved into PCIeDLLTLP class since it also involves RX a bit
        #buffer = RetryBuffer(ratio = ratio, max_tlps = 2 ** len(self.replay_num))
        #unacknowledged_tlp_fifo = SyncFIFOBuffered(12, 4)
#
        #m.submodules += buffer
        #m.submodules += unacknowledged_tlp_fifo
#
        #source_from_buffer = Signal()
        #sink_ready = Signal()
        #m.d.comb += buffer.tlp_source.ready.eq(sink_ready & source_from_buffer)
        #m.d.comb += self.tlp_sink.ready.eq(sink_ready & ~source_from_buffer)
        #sink_valid = Mux(source_from_buffer, buffer.tlp_source.all_valid, self.tlp_sink.all_valid)
        #sink_symbol = [Mux(source_from_buffer, buffer.tlp_source.symbol[i], self.tlp_sink.symbol[i]) for i in range(ratio)]
#
        #self.tlp_sink.connect(buffer.tlp_sink, m.d.comb)
        #m.d.rx += buffer.store_tlp.eq(1) # TODO: Is this a good idea?
        #m.d.rx += buffer.store_tlp_id.eq(self.next_transmit_seq)
        #m.d.rx += buffer.send_tlp_id.eq(unacknowledged_tlp_fifo.r_data)
        #m.d.rx += unacknowledged_tlp_fifo.r_en.eq(0)

        with m.If(~self.dll.up):
            m.d.rx += self.ack_nak_latency_timer.eq(self.ack_nak_latency_timer.reset)
        
        m.d.rx += self.accepts_tlps.eq((self.next_transmit_seq - self.ackd_seq) >= 2048) # mod 4096 is already applied since the signal is 12 bits long

        with m.If(self.timer_running):
            m.d.rx += self.replay_timer.eq(self.replay_timer + 1)

        #with m.FSM(domain = "rx"):
        #    with m.State("Idle"):
        #        m.d.rx += source_from_buffer.eq(0)
#
        #        with m.If(self.replay_timer >= self.replay_timeout):
        #            m.next = "Replay"
        #        
        #        with m.If(NAK received):
        #            m.next = "Replay"
#
        #    with m.State("Replay"):
        #        m.d.rx += source_from_buffer.eq(1)
#
        #        with m.If(buffer.slots_empty):
        #            m.d.rx += source_from_buffer.eq(0)
        #            m.next = "Idle"
        #
        #If ACK received:
        #Delete entry from retry buffer and advance unacknowledged_tlp_fifo
#
        #with m.If(buffer.slots_full):
        #    YEET!
        
        reset_crc = Signal(reset = 1)
        # TODO Warning: Endianness
        crc_input = Signal(32)
        m.submodules.lcrc = lcrc = LCRC(crc_input, reset_crc)

        last_valid = Signal()
        m.d.rx += last_valid.eq(sink_valid)
        last_last_valid = Signal() # TODO: Maybe there is a better way
        m.d.rx += last_last_valid.eq(last_valid)
        last_last_last_valid = Signal() # TODO: Maybe there is a better way 😿 like a longer signal which gets shifted for example
        m.d.rx += last_last_last_valid.eq(last_last_valid)


        tlp_bytes = Signal(8 * self.ratio)
        tlp_bytes_before = Signal(8 * self.ratio)

        with m.If(sink_valid):
            m.d.comb += Cat(tlp_bytes[0 : 8 * ratio]).eq(Cat(sink_symbol)) # TODO: Endianness correct?
            m.d.rx += Cat(tlp_bytes_before[0 : 8 * ratio]).eq(Cat(sink_symbol)) # TODO: Endianness correct?

        with m.Else():
            with m.If(self.nullify):
                m.d.comb += Cat(tlp_bytes[0 : 8 * ratio]).eq(~lcrc.output) # ~~x = x
                m.d.rx += Cat(tlp_bytes_before[0 : 8 * ratio]).eq(~lcrc.output)
                m.d.comb += buffer.delete_tlp.eq(1)
                m.d.comb += buffer.delete_tlp_id.eq(self.next_transmit_seq)

            with m.Else():
                m.d.comb += Cat(tlp_bytes[0 : 8 * ratio]).eq(lcrc.output) # TODO: Endianness correct?
                m.d.rx += Cat(tlp_bytes_before[0 : 8 * ratio]).eq(lcrc.output) # TODO: Endianness correct?


        #m.d.rx += Cat(tlp_bytes[8 * ratio : 2 * 8 * ratio]).eq(Cat(tlp_bytes[0 : 8 * ratio]))

        even_more_delay = [Signal(9) for i in range(4)]

        m.d.rx += unacknowledged_tlp_fifo.w_en.eq(0)

        m.d.comb += sink_ready.eq(0) # TODO: maybe move to rx?

        delayed_symbol = Signal(32)
        m.d.rx += delayed_symbol.eq(Cat(sink_symbol))
        m.d.comb += crc_input.eq(delayed_symbol)

        for i in range(4):
            m.d.rx += self.dllp_source.valid[i].eq(0)

        # TODO: This could be a FSM
        with m.If(self.dllp_source.ready & unacknowledged_tlp_fifo.w_rdy):
            m.d.comb += sink_ready.eq(1) # TODO: maybe move to rx?

            with m.If(~last_valid & sink_valid):
                m.d.comb += reset_crc.eq(0)
                m.d.comb += crc_input.eq(Cat(self.next_transmit_seq[8 : 12], Const(0, shape = 4), self.next_transmit_seq[0 : 8]))
                m.d.rx += even_more_delay[0].eq(Ctrl.STP)
                m.d.rx += even_more_delay[1].eq(self.next_transmit_seq[8 : 12])
                m.d.rx += even_more_delay[2].eq(self.next_transmit_seq[0 : 8])
                m.d.rx += even_more_delay[3].eq(tlp_bytes[8 * 0 : 8 * 1])
                #for i in range(4):
                #    m.d.rx += self.dllp_source.symbol[i].eq(even_more_delay[i])

            with m.Elif(last_valid & sink_valid):
                m.d.comb += reset_crc.eq(0)
                m.d.rx += even_more_delay[0].eq(tlp_bytes_before[8 * 1 : 8 * 2])
                m.d.rx += even_more_delay[1].eq(tlp_bytes_before[8 * 2 : 8 * 3])
                m.d.rx += even_more_delay[2].eq(tlp_bytes_before[8 * 3 : 8 * 4])
                m.d.rx += even_more_delay[3].eq(tlp_bytes[8 * 0 : 8 * 1])
                for i in range(4):
                    m.d.rx += self.dllp_source.symbol[i].eq(even_more_delay[i])
                for i in range(4):
                    m.d.rx += self.dllp_source.valid[i].eq(1)

            with m.Elif(last_valid & ~sink_valid): # Maybe this can be done better and replaced by the two if blocks above
                m.d.comb += reset_crc.eq(0)
                m.d.comb += sink_ready.eq(0) # TODO: maybe move to rx?
                m.d.rx += even_more_delay[0].eq(tlp_bytes_before[8 * 1 : 8 * 2])
                m.d.rx += even_more_delay[1].eq(tlp_bytes_before[8 * 2 : 8 * 3])
                m.d.rx += even_more_delay[2].eq(tlp_bytes_before[8 * 3 : 8 * 4])
                for i in range(4):
                    m.d.rx += self.dllp_source.symbol[i].eq(even_more_delay[i])
                for i in range(4):
                    m.d.rx += self.dllp_source.valid[i].eq(1)

            with m.Elif(last_last_valid & ~sink_valid):
                m.d.rx += self.dllp_source.symbol[3].eq(tlp_bytes[8 * 0 : 8 * 1])

                for i in range(3):
                    m.d.rx += self.dllp_source.symbol[i].eq(even_more_delay[i])

                for i in range(4):
                    m.d.rx += self.dllp_source.valid[i].eq(1)

            with m.Elif(last_last_last_valid & ~sink_valid):
                m.d.comb += sink_ready.eq(0) # TODO: maybe move to rx?
                m.d.rx += self.dllp_source.symbol[0].eq(tlp_bytes_before[8 * 1 : 8 * 2])
                m.d.rx += self.dllp_source.symbol[1].eq(tlp_bytes_before[8 * 2 : 8 * 3])
                m.d.rx += self.dllp_source.symbol[2].eq(tlp_bytes_before[8 * 3 : 8 * 4])

                with m.If(self.nullify):
                    m.d.rx += self.dllp_source.symbol[3].eq(Ctrl.EDB)
                    m.d.rx += self.nullify.eq(0)

                with m.Else():
                    m.d.rx += self.dllp_source.symbol[3].eq(Ctrl.END)
                    m.d.rx += unacknowledged_tlp_fifo.w_data.eq(self.next_transmit_seq)
                    m.d.rx += unacknowledged_tlp_fifo.w_en.eq(1)
                    m.d.rx += self.next_transmit_seq.eq(self.next_transmit_seq + 1)
                
                m.d.rx += replay_timer_running.eq(1) # TODO: Maybe this should be in the Else block above

                for i in range(4):
                    m.d.rx += self.dllp_source.valid[i].eq(1)


        return m