from amaranth import *
from amaranth.build import *
from amaranth.lib.fifo import SyncFIFOBuffered
from .serdes import K, D, Ctrl, PCIeSERDESInterface
from .layouts import ts_layout
from .stream import StreamInterface

# TODO: When TS data changes during TS sending, the sent TS changes. For example when it changes from TS1 to TS2, itll send ...D10.2 D10.2 D5.2 D5.2 which is kinda suboptimal. TS should be buffered.
class PCIePhyTX(Elaboratable):
	"""
	PCIe Transmitter for 1:4 gearing

	Parameters
	----------
	lane : PCIeSERDESInterface
		PCIe lane
	ts : Record(ts_layout)
		Data to send
	fifo_depth : int TODO: remove this, also in RX
		How deep the FIFO to store data to transmit is
	ready : Signal()
		Asserted by LTSSM to enable data transmission
	in_symbols : Signal(18)
		Symbols to send from higher layers
	fifo : SyncFIFOBuffered()
		Data to transmit goes in here
	"""
	def __init__(self, lane : PCIeSERDESInterface, fifo_depth = 256):
		assert lane.ratio == 4
		self.lane = lane
		self.ts = Record(ts_layout)
		self.idle = Signal()
		self.sending_ts = Signal()
		self.ready = Signal()
		self.sink = StreamInterface(9, lane.ratio, name="PHY_Sink")
		self.enable_higher_layers = Signal()
		self.ltssm_L0 = Signal()
		self.idle_symbol = Signal(9, reset = 1)

		self.state = [
			self.ts, self.ltssm_L0, self.enable_higher_layers
		]

	def elaborate(self, platform: Platform) -> Module:
		m = Module()

		lane = self.lane
		ts = self.ts # ts to transmit
		ratio = lane.ratio

		self.start_send_ts = Signal()
		self.idle = Signal()
		self.eidle = Signal(ratio)
		symbols = [lane.tx_symbol[i * 9 : i * 9 + 9] for i in range(ratio)]

		def send(*ssymbols):
			for i in range(ratio):
				m.d.comb += symbols[i].eq(ssymbols[i])
		


		# Store data to be sent
		#m.submodules.fifo = fifo = self.fifo
		#m.d.rx += fifo.r_en.eq(0)

		m.d.rx += self.start_send_ts.eq(0)

		skp_counter = Signal(range(int(1538)))
		skp_accumulator = Signal(4)
		
		# Increase SKP accumulator once counter reaches 325 (SKP between 1180 and 1538 symbol times, here 1300)
		m.d.rx += skp_counter.eq(skp_counter + 1)
		#with m.If((skp_counter << lane.speed) == 650):
		with m.If(skp_counter == 325):
			m.d.rx += skp_counter.eq(0)
			with m.If(skp_accumulator < 15):
				m.d.rx += skp_accumulator.eq(skp_accumulator + 1)

		m.d.comb += self.sink.ready.eq(0) # TODO: Is this necessary?

		# Structure of a TS:
		# COM Link Lane n_FTS Rate Ctrl ID ID ID ID ID ID ID ID ID ID
		with m.FSM(domain="rx"):

			with m.State("IDLE"):

				m.d.rx += self.sending_ts.eq(0)

				# Whether higher levels are sending DLLPs or TLPs
				sending_old = Signal()
				# When a TLP starts, set sending_data to 1 and reset it when it ends.
				# (self.in_symbols[0:9] == Ctrl.SDP) | 
				sending_data = ((self.sink.symbol[0] == Ctrl.STP) | (self.sink.symbol[0] == Ctrl.SDP) # TODO: This might insert SKP sets in the beginning of a TLP since the pipeline takes a while and the ready signal might be buggy
				| sending_old) & ~((self.sink.symbol[3] == Ctrl.END) | (self.sink.symbol[3] == Ctrl.EDB))

				m.d.rx += sending_old.eq(sending_data)
				m.d.rx += self.enable_higher_layers.eq(1)

				m.d.comb += self.sink.ready.eq(self.ltssm_L0)


				last_symbols = [Signal(9) for _ in range(ratio)]

				with m.If(self.sink.all_valid):
					for i in range(ratio):
						m.d.rx += last_symbols[i].eq(self.sink.symbol[i])

				# Send SKP ordered sets when the accumulator is above 0
				#with m.If(skp_accumulator > 0):
				#    m.d.comb += self.sink.ready.eq(0)

				with m.If((skp_accumulator > 0) & ~sending_old & ~sending_data):#(~sending_data | ((last_symbols[3] == Ctrl.END) | (last_symbols[3] == Ctrl.EDB)))):
					m.d.comb += self.sink.ready.eq(0)
					send(Ctrl.COM, Ctrl.SKP, Ctrl.SKP, Ctrl.SKP)
					m.d.rx += [
						self.enable_higher_layers.eq(0),
						skp_accumulator.eq(skp_accumulator - 1),
						self.sending_ts.eq(1),
					]

				with m.Elif(ts.valid):
					m.d.rx += self.sending_ts.eq(1)
					m.d.comb += lane.tx_e_idle.eq(0b0)
					m.next = "TSn-DATA"
					m.d.rx += [
						self.start_send_ts.eq(1)
					]

					# Send PAD symbols if the link/lane is invalid, otherwise send the link/lane number.
					send(
						Ctrl.COM,
						Mux(ts.link.valid, ts.link.number, Ctrl.PAD),
						Mux(ts.lane.valid, ts.lane.number, Ctrl.PAD),
						ts.n_fts
						)

				# Transmit data from higher layers
				with m.Elif(self.ready):
					m.d.comb += self.sink.ready.eq(1)
					for i in range(ratio):
						m.d.comb += symbols[i].eq(Mux(self.sink.valid[i], self.sink.symbol[i], 0))

				# Transmit idle data
				with m.Elif(self.idle):
					send(self.idle_symbol, self.idle_symbol, self.idle_symbol, self.idle_symbol)

				# Otherwise go to electrical idle, if told so
				with m.Else():
					m.d.comb += lane.tx_e_idle.eq(self.eidle)

			ts_symbol = Mux(ts.ts_id, D(5, 2), D(10, 2))

			with m.State("TSn-DATA"):
				send(ts.rate, ts.ctrl, ts_symbol, ts_symbol)
				m.next = "TSn-ID0"

			with m.State("TSn-ID0"):
				send(ts_symbol, ts_symbol, ts_symbol, ts_symbol)
				m.next = "TSn-ID1"

			with m.State("TSn-ID1"):
				send(ts_symbol, ts_symbol, ts_symbol, ts_symbol)
				m.next = "IDLE"

		return m