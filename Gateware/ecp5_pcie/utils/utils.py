import itertools
from amaranth import *
from amaranth.build import *
from amaranth.lib.fifo import AsyncFIFOBuffered, AsyncFIFO, SyncFIFO, SyncFIFOBuffered, FIFOInterface

__all__ = ["Sequencer", "FunctionSequencer", "LFSR", "Resizer", "Rotator", "HexNumber", "UARTDebugger"]

class Sequencer(Elaboratable): # Does signal.eq(value) where values is a 2D array, values[m] being the values for the mth signal and values[m][n] being the values for the mth signal at the nth step. times is the clock cycle number of each occurence
	def __init__(self, signals, values, done, reset, times=lambda x : x):
		self.signals = signals
		self.values = values
		self.reset = reset
		self.done = done
		self.times = times
		self.ports = [
			self.signals,
			self.reset,
			self.done,
		]
		len0 = len(values[0])
		self.length = len0
		for row in values:
			assert len(row) == len0

	def elaborate(self, platform):
		m = Module()
		maxT = 0
		for i in range(0, self.length):
			maxT = max(maxT, self.times[i])
		
		counter = Signal(range(maxT + 1), reset=maxT)
		
		for i in range(0, self.length):
			with m.If(counter == int(self.times[i])):
				for j in range(0, len(self.signals)):
					m.d.sync += self.signals[j].eq(self.values[j][i])
		
		with m.If(counter < maxT):
			m.d.sync += counter.eq(counter + 1)
			m.d.comb += self.done.eq(0)
		with m.If(counter == maxT):
			m.d.comb += self.done.eq(1)
			with m.If(self.reset == 1):
				m.d.sync += counter.eq(0)
		return m

class FunctionSequencer(Elaboratable): # Does signal.eq(value) where points is list of tuples, functions[n][0] being the time in clock cycles when the function is executed and functions[n][1] being the function executed at the nth step on sync domain. times is the clock cycle number of each occurence
	def __init__(self, points, done, reset, startByDefault=False):
		self.points = points
		self.reset = reset
		self.startByDefault = startByDefault
		self.done = done
		self.ports = [
			self.reset,
			self.done,
		]
		self.length = len(points)

	def elaborate(self, platform):
		m = Module()
		maxT = 0
		for i in range(0, self.length):
			maxT = max(maxT, self.points[i][0])
		
		counter = Signal(range(maxT + 1), reset=0 if self.startByDefault else maxT)
		
		for i in range(0, self.length):
			with m.If(counter == int(self.points[i][0])):
				m.d.sync += self.points[i][1]
		
		with m.If(counter < maxT):
			m.d.sync += counter.eq(counter + 1)
			m.d.comb += self.done.eq(0)
		with m.If(counter == maxT):
			m.d.comb += self.done.eq(1)
			with m.If(self.reset == 1):
				m.d.sync += counter.eq(0)
		return m

class LFSR(Elaboratable):
	def __init__(self, out, domain="sync", taps=[25,16,14,13,11], run=1, reset=1, skip = 0):
		self.out = out
		self.taps = taps
		self.run = run
		self.reset = reset
		self.domain = domain
		self.skip = skip
		self.ports = [
			self.out,
			self.run,
		]

	def elaborate(self, platform):
		m = Module()
		
		skipLFSR = self.reset
		for i in range(0, self.skip):
			skipLFSR = skipLFSR << 1 #Order may be wrong
			val = 0
			for tap in self.taps:
				val ^= (skipLFSR >> tap) & 1 == 1
			skipLFSR += val
		
		lfsr = Signal(max(self.taps) + 1, reset=skipLFSR & ((1 << (max(self.taps) + 1)) - 1))
		m.d.comb += self.out.eq(lfsr[0])
		sig0 = lfsr[self.taps[0]]
		
		for tap in self.taps[1:]:
			sig0 ^= lfsr[tap]
		
		with m.If(self.run):
			m.d[self.domain] += lfsr.eq(lfsr << 1) #Order may be wrong
			m.d[self.domain] += lfsr[0].eq(sig0)
		
		return m

class Resizer(Elaboratable):
	def __init__(self, datain, dataout, datastep, enable=1): #datastep toggled for 1 cycle when new data is there when enlarging or when new data needs to be sampled when shrinking.
		if len(datain) > len(dataout):
			assert len(datain) % len(dataout) == 0
			self.enlarge = False
			self.ratio = int(len(datain) / len(dataout))
			self.step = len(dataout)
		else:
			assert len(dataout) % len(datain) == 0
			self.enlarge = True
			self.ratio = int(len(dataout) / len(datain))
			self.step = len(datain)
		
		self.datain = datain
		self.dataout = dataout
		self.enable = enable
		self.datastep = datastep
		self.ports = [
			self.datain,
			self.dataout,
			self.enable,
			self.datastep,
		]

	def elaborate(self, platform):
		m = Module()
		
		datain = self.datain
		dataout = self.dataout
		step = self.step
		ratio = self.ratio
		datastep = self.datastep
		counter = Signal(range(ratio))
		databuf = Signal(len(dataout))
		with m.If(self.enable == 1):
			with m.If(counter >= ratio - 1):
				m.d.sync += counter.eq(0)
				m.d.comb += datastep.eq(1) #Try to put in sync without error
				if self.enlarge:
					m.d.sync += dataout.eq(databuf)
			with m.Else():
				m.d.sync += counter.eq(counter + 1)
				m.d.comb += datastep.eq(0)
			if self.enlarge:
				m.d.sync += databuf.word_select(counter, step).eq(datain)
			else:
				m.d.sync += dataout.eq(datain.word_select(counter, step))
		with m.Else():
			m.d.comb += datastep.eq(0)
		return m

class Rotator(Elaboratable):
	def __init__(self, datain, dataout, rotation=0, comb=True):
		assert len(datain) == len(dataout)
		
		self.datain = datain
		self.dataout = dataout
		self.rotation = rotation
		self.comb = comb
		
		self.ports = [
			self.datain,
			self.dataout,
			self.rotation,
		]

	def elaborate(self, platform):
		m = Module()
		
		length = len(self.datain)
		with m.Switch(self.rotation):
			for i in range(length):
				with m.Case(i):
					if self.comb:
						m.d.comb += self.dataout.eq(Cat(self.datain[i:length], self.datain[0:i]))
					else:
						m.d.sync += self.dataout.eq(Cat(self.datain[i:length], self.datain[0:i]))
		
		return m

class HexNumber(Elaboratable):
	def __init__(self, data, ascii, comb=True):
		assert len(data) == 4
		assert len(ascii) == 8
		
		self.data = data
		self.ascii = ascii
		self.comb = comb
		
		self.ports = [
			self.data,
			self.ascii,
		]

	def elaborate(self, platform):
		m = Module()
		
		with m.Switch(self.data):
			for i in range(0, 10):
				with m.Case(i):
					if self.comb:
						m.d.comb += self.ascii.eq(ord('0') + self.data)
					else:
						m.d.sync += self.ascii.eq(ord('0') + self.data)
			for i in range(10, 16):
				with m.Case(i):
					if self.comb:
						m.d.comb += self.ascii.eq(ord('A') + self.data - 10)
					else:
						m.d.sync += self.ascii.eq(ord('A') + self.data - 10)
		
		return m

class UARTDebugger(Elaboratable):
	"""UART Debugger. Once a symbol comes in over the UART, it records data in a FIFO at sync rate and then sends them over UART.
	Parameters
	----------
	uart : AsyncSerial
		UART interface from amaranth_stdio
	words : int
		Number of bytes
	depth : int
		Number of samples stored in FIFO
	data : Signal, in
		Data to sample, 8 * words wide
	data_domain : string
		Input clock domain
	enable : Signal, in
		Enable sampling
		
	"""
	def __init__(self, uart, words, depth, data, data_domain="sync", enable=1, timeout=-1):
		assert(len(data) == words * 8)
		self.uart = uart
		self.words = words
		self.depth = depth
		self.data = data
		self.data_domain = data_domain
		self.enable = enable
		self.timeout = timeout

	def elaborate(self, platform: Platform) -> Module:
		m = Module()

		uart = self.uart
		words = self.words
		depth = self.depth
		data = self.data
		if(self.timeout >= 0):
			timer = Signal(range(self.timeout + 1), reset=self.timeout)
		word_sel = Signal(range(2 * words), reset = 2 * words - 1)
		fifo = AsyncFIFOBuffered(width=8 * words, depth=depth, r_domain="sync", w_domain=self.data_domain)
		m.submodules += fifo

		m.d.comb += fifo.w_data.eq(data)

		def sendByteFSM(byte, nextState):
			sent = Signal(reset=0)
			with m.If(uart.tx.rdy):
				with m.If(sent == 0):
					m.d.sync += uart.tx.data.eq(byte)
					m.d.sync += uart.tx.ack.eq(1)
					m.d.sync += sent.eq(1)
				with m.If(sent == 1):
					m.d.sync += uart.tx.ack.eq(0)
					m.d.sync += sent.eq(0)
					m.next = nextState
		
		with m.FSM():
			with m.State("Wait"):
				m.d.sync += uart.rx.ack.eq(1)
				with m.If(uart.rx.rdy):
					m.d.sync += uart.rx.ack.eq(0)
					if self.timeout >= 0:
						m.d.sync += timer.eq(self.timeout)
					m.next = "Pre-Collect"
			with m.State("Pre-Collect"):
				sendByteFSM(ord('\n'), "Collect")
			with m.State("Collect"):
				with m.If(~fifo.w_rdy | ((timer == 0) if self.timeout >= 0 else 0)):
					m.d.comb += fifo.w_en.eq(0)
					m.next = "Transmit-1"
				with m.Else():
					m.d.comb += fifo.w_en.eq(self.enable)
					if self.timeout >= 0:
						m.d.sync += timer.eq(timer - 1)
			with m.State("Transmit-1"):
				with m.If(fifo.r_rdy):
					m.d.sync += fifo.r_en.eq(1)
					m.next = "Transmit-2"
				with m.Else():
					m.next = "Wait"
			with m.State("Transmit-2"):
				m.d.sync += fifo.r_en.eq(0)
				m.next = "TransmitByte"
			with m.State("TransmitByte"):
				sent = Signal(reset=0)
				with m.If(uart.tx.rdy):
					with m.If(sent == 0):
						hexNumber = HexNumber(fifo.r_data.word_select(word_sel, 4), Signal(8))
						m.submodules += hexNumber
						m.d.sync += uart.tx.data.eq(hexNumber.ascii)
						m.d.sync += uart.tx.ack.eq(1)
						m.d.sync += sent.eq(1)
					with m.If(sent == 1):
						m.d.sync += uart.tx.ack.eq(0)
						m.d.sync += sent.eq(0)
						with m.If(word_sel == 0):
							m.d.sync += word_sel.eq(word_sel.reset)
							m.next = "Separator"
						with m.Else():
							m.d.sync += word_sel.eq(word_sel - 1)
				with m.Else():
					m.d.sync += uart.tx.ack.eq(0)
			with m.State("Separator"):
				sendByteFSM(ord('\n'), "Transmit-1")
		return m

class UARTDebugger2(Elaboratable):
	"""UART Debugger. It records data in a FIFO at sync rate and once a symbol comes in over the UART it sends the FIFO contents over UART.
	Parameters
	----------
	uart : AsyncSerial
		UART interface from amaranth_stdio
	words : int
		Number of bytes
	depth : int
		Number of samples stored in FIFO
	data : Signal, in
		Data to sample, 8 * words wide
	data_domain : string
		Input clock domain
	enable : Signal, in
		Enable sampling
		
	"""
	def __init__(self, uart, words, depth, data, data_domain="sync", enable=1, timeout=-1):
		assert(len(data) == words * 8)
		self.uart = uart
		self.words = words
		self.depth = depth
		self.data = data
		self.data_domain = data_domain
		self.enable = enable
		self.timeout = timeout

	def elaborate(self, platform: Platform) -> Module:
		m = Module()

		uart = self.uart
		words = self.words
		depth = self.depth
		data = self.data
		if(self.timeout >= 0):
			timer = Signal(range(self.timeout + 1), reset=self.timeout)
		word_sel = Signal(range(2 * words), reset = 2 * words - 1)
		fifo = AsyncFIFOBuffered(width=8 * words, depth=depth, r_domain="sync", w_domain=self.data_domain)
		m.submodules += fifo

		m.d.comb += fifo.w_data.eq(data)

		def sendByteFSM(byte, nextState):
			sent = Signal(reset=0)
			with m.If(uart.tx.rdy):
				with m.If(sent == 0):
					m.d.sync += uart.tx.data.eq(byte)
					m.d.sync += uart.tx.ack.eq(1)
					m.d.sync += sent.eq(1)
				with m.If(sent == 1):
					m.d.sync += uart.tx.ack.eq(0)
					m.d.sync += sent.eq(0)
					m.next = nextState
		
		with m.FSM():
			with m.State("Collect"):
				with m.If(~fifo.w_rdy | ((timer == 0) if self.timeout >= 0 else 0)):
					m.d.comb += fifo.w_en.eq(0)
					m.next = "Wait"
				with m.Else():
					m.d.comb += fifo.w_en.eq(self.enable)
					if self.timeout >= 0:
						m.d.sync += timer.eq(timer - 1)

			with m.State("Wait"):
				m.d.sync += uart.rx.ack.eq(1)
				with m.If(uart.rx.rdy):
					m.d.sync += uart.rx.ack.eq(0)
					if self.timeout >= 0:
						m.d.sync += timer.eq(self.timeout)
					m.next = "Pre-Transmit"

			with m.State("Pre-Transmit"):
				sendByteFSM(ord('\n'), "Transmit-1")

			with m.State("Transmit-1"):
				with m.If(fifo.r_rdy):
					m.d.sync += fifo.r_en.eq(1)
					m.next = "Transmit-2"
				with m.Else():
					m.next = "Collect"

			with m.State("Transmit-2"):
				m.d.sync += fifo.r_en.eq(0)
				m.next = "TransmitByte"

			with m.State("TransmitByte"):
				sent = Signal(reset=0)
				with m.If(uart.tx.rdy):
					with m.If(sent == 0):
						hexNumber = HexNumber(fifo.r_data.word_select(word_sel, 4), Signal(8))
						m.submodules += hexNumber
						m.d.sync += uart.tx.data.eq(hexNumber.ascii)
						m.d.sync += uart.tx.ack.eq(1)
						m.d.sync += sent.eq(1)
					with m.If(sent == 1):
						m.d.sync += uart.tx.ack.eq(0)
						m.d.sync += sent.eq(0)
						with m.If(word_sel == 0):
							m.d.sync += word_sel.eq(word_sel.reset)
							m.next = "Separator"
						with m.Else():
							m.d.sync += word_sel.eq(word_sel - 1)
				with m.Else():
					m.d.sync += uart.tx.ack.eq(0)

			with m.State("Separator"):
				sendByteFSM(ord('\n'), "Transmit-1")

			with m.State("TransmitEnd"):
				sendByteFSM(ord('Z'), "Collect")
		return m

class UARTDebugger3(Elaboratable):
	"""UART Debugger. It records data in a FIFO at sync rate and once a symbol comes in over the UART it sends the FIFO contents over UART, whatever is in there.
	Parameters
	----------
	uart : AsyncSerial
		UART interface from amaranth_stdio
	words : int
		Number of bytes
	depth : int
		Number of samples stored in FIFO
	data : Signal, in
		Data to sample, 8 * words wide
	data_domain : string
		Input clock domain
	enable : Signal, in
		Enable sampling
		
	"""
	def __init__(self, uart, words, depth, data, data_domain="sync", enable=1):
		assert(len(data) == words * 8)
		self.uart = uart
		self.words = words
		self.depth = depth
		self.data = data
		self.data_domain = data_domain
		self.enable = enable

	def elaborate(self, platform: Platform) -> Module:
		m = Module()

		uart = self.uart
		words = self.words
		depth = self.depth
		data = self.data
		
		word_sel = Signal(range(2 * words), reset = 2 * words - 1)
		fifo = AsyncFIFOBuffered(width=8 * words, depth=depth, r_domain="sync", w_domain=self.data_domain)
		m.submodules += fifo

		m.d.comb += fifo.w_data.eq(data)

		def sendByteFSM(byte, nextState):
			sent = Signal(reset=0)
			with m.If(uart.tx.rdy):
				with m.If(sent == 0):
					m.d.sync += uart.tx.data.eq(byte)
					m.d.sync += uart.tx.ack.eq(1)
					m.d.sync += sent.eq(1)
				with m.If(sent == 1):
					m.d.sync += uart.tx.ack.eq(0)
					m.d.sync += sent.eq(0)
					m.next = nextState
		
		with m.FSM():
			with m.State("Collect"):
				m.d.comb += fifo.w_en.eq(self.enable)

				m.d.sync += uart.rx.ack.eq(1)
				with m.If(uart.rx.rdy):
					m.d.comb += fifo.w_en.eq(0)
					m.d.sync += uart.rx.ack.eq(0)
					m.next = "Pre-Transmit"

			with m.State("Pre-Transmit"):
				sendByteFSM(ord('\n'), "Transmit-1")

			with m.State("Transmit-1"):
				with m.If(fifo.r_rdy):
					m.d.sync += fifo.r_en.eq(1)
					m.next = "Transmit-2"
				with m.Else():
					m.next = "Collect"

			with m.State("Transmit-2"):
				m.d.sync += fifo.r_en.eq(0)
				m.next = "TransmitByte"

			with m.State("TransmitByte"):
				sent = Signal(reset=0)
				with m.If(uart.tx.rdy):
					with m.If(sent == 0):
						hexNumber = HexNumber(fifo.r_data.word_select(word_sel, 4), Signal(8))
						m.submodules += hexNumber
						m.d.sync += uart.tx.data.eq(hexNumber.ascii)
						m.d.sync += uart.tx.ack.eq(1)
						m.d.sync += sent.eq(1)
					with m.If(sent == 1):
						m.d.sync += uart.tx.ack.eq(0)
						m.d.sync += sent.eq(0)
						with m.If(word_sel == 0):
							m.d.sync += word_sel.eq(word_sel.reset)
							m.next = "Separator"
						with m.Else():
							m.d.sync += word_sel.eq(word_sel - 1)
				with m.Else():
					m.d.sync += uart.tx.ack.eq(0)

			with m.State("Separator"):
				sendByteFSM(ord('\n'), "Transmit-1")

			with m.State("TransmitEnd"):
				sendByteFSM(ord('Z'), "Collect")
		return m

class __UARTDebuggerWrapper: # Not really usable, amaranth part of Gateware needs to be executed to determine signal sizes for this to be usable (and the read function isn't finished).
	"""UART Debugger Wrapper. It wraps an UARTDebugger2 for ease of use.
	Parameters
	----------
	depth : int
		Maximum number of samples stored in the FIFO buffer
	"""
	def __init__(self, depth):
		assert(len(data) == words * 8)
		self.depth = depth
	
	"""Initialize FPGA side, add return value of this function as a submodule
	Parameters
	----------
	uart : AsyncSerial
		UART interface from amaranth_stdio
	data : Dictionary of Name, Signal, in
		Data to sample
	data_domain : string
		Input clock domain
	enable : Signal, in
		Enable sampling
	"""
	def init_fpga(self, uart, data, data_domain="sync", enable=1, timeout=-1):
		current_bit = 0
		data_format = [] # Array of [name, position, length]
		signals     = [] # Signals to Cat

		for key, value in data:
			data_format.append([key, current_bit, len(value)])
			current_bit += len(value)
			signals.append(value)
		
		signals.append(Signal(len(Cat(signals)) % 8)) # Round it up to length 8 * n

		self.debugger = debugger = UARTDebugger2(uart, int(len(Cat(signals)) / 8), self.depth, Cat(signals), data_domain, enable, timeout)
		self.data_format = data_format
		return debugger

	"""Read data from the UARTDebugger2
	Parameters
	----------
	callback : Function
		It is called with a dictionary of all signals values, it is called once for each sample.
	"""
	def read(callback):
		port = serial.Serial(port=glob("/dev/serial/by-id/usb-FTDI_Lattice_ECP5_5G_VERSA_Board_*-if01-port0")[0], baudrate=1000000)
		port.write(b"\x00")

		while True:
			#while True:
			#    if port.read(1) == b'\n': break
			if port.read(1) == b'\n': break
		
		for x in range(self.depth):
			chars = port.read(5 * 2 + 1)
			word = int(chars, 16)

class VariableLogger(Elaboratable):
	"""Logs data at a variable rate into a FIFO
	Write domain is 'sync', use DomainRenamer
	Parameters
	----------
	depth : int
		Number of samples stored in FIFO
	data : Signal, in
		Data to sample
	data_domain : string
		Input clock domain
	fifo : FIFOInterface
		FIFO to store data into, `w_domain` needs to be the same domain as the logic in this (sync), `width` needs to be `len(data)`

	Attributes
	----------
	size : int
		Insert `size` number of bits into the FIFO in this cycle
	flush: Signal()
		Put internal buffer and the part of `data` which fits into FIFO and reset pointer
		
	"""
	def __init__(self, data, fifo : FIFOInterface):
		assert fifo.width == len(data)
		self.data = data
		self.size = Signal(range(len(data)))
		self.fifo = fifo
		self.flush = Signal()

	def elaborate(self, platform: Platform) -> Module:
		m = Module()
		
		#m.submodules += self.fifo
		buffer = Signal(len(self.data)) # Leftovers for next cycle
		pointer = Signal(range(len(self.data)))

		m.d.sync += self.fifo.w_en.eq(0)
		windowed_data = (((1 << self.size) - 1) # size = 8 -> 0b11111111
		                           & self.data) # data = 0bxxxxxxx11001001 -> 0b000000011001001

		with m.If(self.flush):
			m.d.sync += self.fifo.w_en.eq(1)
			m.d.sync += self.fifo.w_data.eq((windowed_data << pointer) | buffer) # pointer = 4 : 0b000110010010000, buffer = 0b000000000000111 -> 0b000110010010111
			m.d.sync += buffer.eq(0)
			m.d.sync += pointer.eq(0)

		with m.Elif(self.size > 0):
			with m.If(pointer + self.size > len(self.data)): # Maybe >= ? This could be simplified if len(self.data) is constrained to 2^n
				m.d.sync += pointer.eq(pointer + self.size - len(self.data))
				m.d.sync += self.fifo.w_en.eq(1)
				m.d.sync += self.fifo.w_data.eq((windowed_data << pointer) | buffer) # pointer = 4 : 0b000110010010000, buffer = 0b000000000000111 -> 0b000110010010111

				# Add the remainder
				already_added = len(self.data) - pointer # In case this is incorrect: maybe pointer + 1?
				shifted_data = windowed_data >> already_added
				m.d.sync += buffer.eq(
					((1 << (self.size - already_added)) - 1)
					& shifted_data
				)
			
			with m.Else():
				m.d.sync += pointer.eq(pointer + self.size)
				m.d.sync += buffer.eq((windowed_data << pointer) | buffer) # pointer = 4 : 0b000110010010000, buffer = 0b000000000000111 -> 0b000110010010111

		return m
	
	@classmethod
	def test_fifo_type(cls, fifo):
		m = Module()

		data = Signal(fifo.width)
		depth = 14
		m.submodules.fifo = fifo
		m.submodules.dut = dut = cls(data, fifo)

		sim = Simulator(m)
		sim.add_clock(1E-11, domain = "sync")

		test_cases = [[[10, 8091], [5, 1919], [11, 5439]], [[9, 3025], [11, 242]], [[11, 6136], [4, 7251], [6, 6463], [2, 5973], [9, 143], [5, 6493], [2, 1092], [6, 4544], [7, 6162], [5, 7930], [6, 5941], [9, 390], [6, 1856], [6, 7019], [6, 550], [3, 2208], [5, 3160], [9, 4693], [6, 4476], [6, 2096], [3, 3641], [7, 4112], [7, 1750], [4, 7813], [5, 1714], [9, 7126], [2, 4334], [8, 3596]]]

		for i in range(512):
			test_data = []
			test_position = 0
			end_position = random.randint(0, len(data) * (fifo.depth - 1))

			while test_position < end_position:
				length = random.randint(2, len(data) - 2)
				t_data = random.randint(0, 2 ** len(data))
				test_data.append([length, t_data])
				test_position += length
			
			test_cases.append(test_data)
		
		def process():
			for test_data in test_cases:
				expected_test_result = 0
				test_position = 0
				
				for length, t_data in test_data:
					expected_test_result |= (t_data & (2 ** length - 1)) << test_position
					test_position += length
					yield dut.size.eq(length)
					yield data.eq(t_data)
					yield

				yield dut.size.eq(0)
				yield dut.flush.eq(1) # Ensure all data is in the FIFO
				yield
				yield dut.flush.eq(0)
				yield
				yield
				
				while not (yield dut.fifo.r_rdy):
					yield
					
				actual_test_result = 0
				test_position = 0

				while (yield dut.fifo.r_rdy):
					r_data = (yield dut.fifo.r_data)
					actual_test_result |= r_data << test_position
					test_position += len(data)
					yield
					yield dut.fifo.r_en.eq(1)
					yield
					yield dut.fifo.r_en.eq(0)
					yield

				yield
				
				if not actual_test_result ^ expected_test_result == 0:
					print(f"Test {cls.__name__} with {type(fifo).__name__} not passed!")
					print(test_data)
					print(bin(expected_test_result))
					print(bin(actual_test_result))
					print(bin(expected_test_result ^ actual_test_result))
					exit()

		sim.add_sync_process(process, domain="sync")

		with sim.write_vcd("test.vcd", "test.gtkw"):
			sim.run()

		print(f"Test {cls.__name__} with {type(fifo).__name__} passed!")
	
	@classmethod
	def test(cls):
		# Tests with FWFT = True
		cls.test_fifo_type(AsyncFIFO        (width = 13, depth = 14, w_domain = "sync", r_domain = "sync"))
		cls.test_fifo_type(AsyncFIFOBuffered(width = 13, depth = 14, w_domain = "sync", r_domain = "sync"))
		cls.test_fifo_type( SyncFIFO        (width = 13, depth = 14))
		cls.test_fifo_type( SyncFIFOBuffered(width = 13, depth = 14))

if __name__ == "__main__":
	from amaranth.sim import *
	import random
	VariableLogger.test()