from amaranth import *
from amaranth.build import *


__all__ = ["PCIeLFSR"]


class PCIeLFSR(Elaboratable):
	"""
	PCIe Linear Feedback Shift Register for scrambling

	Parameters
	----------
	bytes : int
		Number of bytes of scrambling data to produce
	reset : Signal
		Reset LFSR, should be 'symbol == Ctrl.COM'
	advance : Signal
		Advance LFSR, should be 'symbol != Ctrl.SKP'
	
	output : Signal(9 * bytes)
		output data for scrambling. XOR symbols with this to scramble. 9th bit is 0
	"""
	def __init__(self, bytes, reset, advance):
		self.reset = reset
		self.advance = advance
		self.output = Signal(9 * bytes)
		#self.count = Signal(32)
		self.__bytes = bytes

	def elaborate(self, platform: Platform) -> Module:
		m = Module()

		def calculate_lfsr(advances):
			state = 0xFFFF
			for _ in range(advances):
				state = ((state >> 8) | ((state & 0xFF) << 8)) ^ ((state & 0xFF00) >> 5) ^ ((state & 0xFF00) >> 4) ^ ((state & 0xFF00) >> 3)
				
			return state

		def apply_lfsr(in_state):
			return Cat(in_state[8:16], in_state[0:8]) ^ Cat(Const(0, 3), in_state[8:16]) ^ Cat(Const(0, 4), in_state[8:16]) ^ Cat(Const(0, 5), in_state[8:16])

		#states = [Signal(16, reset=calculate_lfsr(i)) for i in range(self.__bytes)]
		states = [Signal(16, reset=0xFFFF) for i in range(self.__bytes)]# * self.__bytes


		for i in range(0, self.__bytes - 1):
			m.d.comb += states[i + 1].eq(apply_lfsr(states[i]))


		with m.If(self.reset):
			with m.If(self.advance):
				m.d.rx += states[0].eq([0, 0xFFFF, 0xE817, 0x0328, 0x284B, 0x4DE8, 0xE755, 0x404F, 0x4140][self.__bytes]) # TODO: This is a hack. Please fix. It is the next state after 0xFFFF. It happens when there is 'COM x' where x is not SKP.
			with m.Else():
				m.d.rx += states[0].eq(0xFFFF) # When x is SKP, it can go straight to 0xFFFF.
				# Because when its not SKP, it already needs to advance by 1 cycle. With COM SKP, the number of LFSR advances look like this, symbol 1 besides symbol 2:
				# 0 1
				# 2 3
				# 4 5
				# and so on. But for example with COM D0.0 it goes like
				# 1 2
				# 3 4
				# 5 6
				# afterwards, where it is shifted by ½ clock cycle. In the PCIeScrambler, before the beginning of the thing above, the second symbol gets scrambled with 0xFF.
			#for i in range(1, self.__bytes - 1):
			#    m.d.comb += states[i + 1].eq(apply_lfsr(states[i]))
		with m.Elif(self.advance):
			m.d.rx += states[0].eq(apply_lfsr(states[self.__bytes - 1]))
			#for i in range(self.__bytes):
			#    if i == self.__bytes - 1:
			#        m.d.rx += states[0].eq(apply_lfsr(states[i]))
			#    else:
			#        m.d.comb += states[i + 1].eq(apply_lfsr(states[i]))
		
		for i in range(self.__bytes):
			m.d.comb += self.output.word_select(i, 9).eq(states[i][15:7:-1])

		return m