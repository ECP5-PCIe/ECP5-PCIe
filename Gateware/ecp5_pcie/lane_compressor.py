from amaranth import *
from amaranth.build import *
from .layouts import ts_layout
from .serdes import Ctrl

class State(IntEnum):
	Raw_Data = 0
	Compression_Info = 1

class DataType(IntEnum):
	TS = 0
	SKP = 1
	DLLP = 2
	TLP = 3

class RawLaneCompressor_x4(Elaboratable):
	"""
	Compresses x4 raw lane data with a simple algorithm
	"""
	def __init__(self):
		width = 9
		length = 4
		gearing = 4
		out_size = width * gearing
		self.input    = Signal(width * gearing)
		self.output   = Signal(out_size)
		self.width    = width
		self.length   = length
		self.gearing  = gearing
	
	def elaborate(self, platform):
		m = Module()

		input_buffer = [Signal(len(self.input)) for i in range(2 * self.length)]

		for i in range(2 * self.length - 1):
			m.d.sync += input_buffer[i + 1].eq(input_buffer[i])

		m.d.sync += input_buffer[0].eq(self.input)

		last_ts = Signal(9 * 7)
		last_dllp = Signal(9 * 8)
		data_type = Signal(DataType)

		current_ts = Cat(input_buffer[3], input_buffer[2][0 : 27])
		current_dllp = Cat(input_buffer[3], input_buffer[2])



		with m.FSM():
			with m.State("Collect"):
				with m.If(input_buffer[3][0 : 9] == Ctrl.COM):
					with m.If(input_buffer[3][27 : 36] == Ctrl.SKP): # SKP
						m.d.sync += data_type.eq(DataType.SKP)
						m.next = "Send Compressed"

					with m.Elif(input_buffer[3][36] == 0): # TS
						m.d.sync += data_type.eq(DataType.TS)
						m.d.sync += ts.eq(current_ts)
						m.next = "Send Compressed"

				with m.Elif(input_buffer[3][0 : 9] == Ctrl.SDP):
					m.d.sync += data_type.eq(DataType.DLLP)
					m.d.sync += last_dllp.eq(current_dllp)
					m.next = "Send Compressed"

				with m.Elif(input_buffer[3][0 : 9] == Ctrl.STP):
					m.next = "Send TLP"

			with m.State("Send TLP"):
				m.d.sync += self.output.eq(DataType.TLP)
				m.next = "Sending TLP"

			with m.State("Sending TLP"):
				m.d.sync += self.output.eq(input_buffer[5])

				with m.If(input_buffer[5][27:36] == Ctrl.END):
					m.next = "Collect"

			with m.State("Send Compressed"):

		return m