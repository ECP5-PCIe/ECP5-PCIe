from amaranth import *
from amaranth.build import *
from amaranth.lib.fifo import SyncFIFOBuffered

from enum import IntEnum
from .layouts import dllp_layout
from .serdes import K, D, Ctrl
from .crc import CRC
from .stream import StreamInterface

class PCIeVirtualTLPGenerator(Elaboratable):
	def __init__(self, ratio = 4):
		self.tlp_source = StreamInterface(8, ratio, name="TLP_Gen_Out")
		self.ratio = ratio

	def elaborate(self, platform: Platform) -> Module:
		m = Module()

		ratio = self.ratio

		timer = Signal(9)

		test_tlp_1 = [0x44, 0, 0, 1, 0, 0, 0, 0xf, 1, 0, 0, 0x24, 0xFF, 0xFF, 0xFF, 0xFF] # CfgWr0 (as received from ROCKPro64)
		test_tlp_2 = [0x4, 0, 0, 1, 0, 0, 0, 0xf, 1, 0, 0, 0x24] # CfgRd0 (as received from ROCKPro64)
		#test_tlp = [0x74, 0, 0, 1, 0, 0xE2, 0, 0x50, 0, 0, 0, 0, 0, 0, 0, 0, 0xA, 0, 0, 0]
		assert (len(test_tlp_1) // 4) * 4 == len(test_tlp_1)
		assert (len(test_tlp_2) // 4) * 4 == len(test_tlp_2)
		#test_tlp = [1,2,3,4,5,6,7,8,9,10,11,12]

		with m.If(self.tlp_source.ready):
			m.d.rx += timer.eq(timer + 1)
			#with m.If(timer < 128): # TODO: If this value is 64 it goes to Recovery
			#	for i in range(ratio):
			#		m.d.rx += self.tlp_source.symbol[i].eq(timer * ratio + i)
			#		m.d.rx += self.tlp_source.valid[i].eq(1)

			with m.If(timer == 2):
				pass

			for j in range(len(test_tlp_1) // 4):
				with m.Elif(timer == 10 + j):
					for i in range(ratio):
						m.d.rx += self.tlp_source.symbol[i].eq(test_tlp_1[i + j * 4])
						m.d.rx += self.tlp_source.valid[i].eq(1)

			for j in range(len(test_tlp_2) // 4):
				with m.Elif(timer == 300 + j):
					for i in range(ratio):
						m.d.rx += self.tlp_source.symbol[i].eq(test_tlp_2[i + j * 4])
						m.d.rx += self.tlp_source.valid[i].eq(1)

			with m.Else():
				for i in range(ratio):
					m.d.rx += self.tlp_source.valid[i].eq(0)

		return m