from amaranth import *
from amaranth.build import *
from amaranth.sim import Simulator
from ecp5_pcie.serdes import K, D, Ctrl, PCIeScrambler, PCIeSERDESInterface, compose

Symbols = [
	0, 0, 0, 0,
	Ctrl.COM, Ctrl.SKP, Ctrl.SKP, Ctrl.SKP,
	0xff, 0x17, 0xc0, 0x14,
	0xb2, 0xe7, 0x02, 0x82,
	0x72, 0x6e, 0x28, 0xa6, # 15 / 12
	0xbe, 0x6d, 0xbf, 0x8d,
	0xbe, 0x40, 0xa7, 0xe6, # a7 19th symbol
	0x2c, 0xd3, 0xe2, 0xb2,
	0x07, 0x02, 0x77, 0x2a,
	0, 0, 0, 0,
	Ctrl.COM, 0x00, 0x00, 0xff,
	0x42, 0x00, 0x45, 0x45,
	0x45, 0x45, 0x45, 0x45,
	0x45, 0x45, 0x45, 0x45, # 15
	0x8d, 0xbe, 0x40, 0xa7, # a7 19th symbol
	0xe6, 0x2c, 0xd3, 0xe2,
	0xb2, 0x07, 0x02, 0x77
	]

Reference = [
     0,     0,     0,     0,
     0,     0,     0,     0,
   178,   115,   256,    16,
   444,   142,    71,    35,
     0,     0,     0,     0,
     0,     0,     0,     0,
     0,     0,     0,     0,
     0,     0,     0,     0,
     0,     0,     0,     0,
     0,     0,     0,     0,
     0,     0,     0,     0,
   205,    26,    47,    28,
   444,   127,   265,     9,
    86,    89,   424,     8,
   199,   283,   138,    13,
   227,   125,   266,    31,
     0,     0,     0,     0,

     0,     0,     0,     0,
     0,     0,     0,     0,
   152,   101,   141,    25,
    82,   336,   407,    10,
     3,   334,   296,    25,
   144,   361,   273,    13,
    97,   104,   186,     0,
    92,    21,   182,    13,
    72,   279,   139,     8,
   137,    30,     3,     3,
   213,   100,   385,     7,
   148,   362,   186,     9,
   127,    16,   413,     8,
    78,   329,    34,    14,
   108,   106,   129,     4,
    68,    36,   418,    30,
    39,    97,   154,     2,
    64,    76,   259,    26,
]


m = Module()

m.submodules.lane = lane = PCIeSERDESInterface(4)
m.submodules.scrambler = scrambler = PCIeScrambler(lane)


sim = Simulator(m)
sim.add_clock(1 / 125e6, domain="rx")# For NextPNR, set the maximum clock frequency such that errors are given




def process():
	data = []

	yield scrambler.enable.eq(1)
	def printl(val):
		for i in range(4):
			sym = (val >> (10 * i)) & 0x1FF
			print(f"{sym:6},", end="")

		print()

	for i in range(len(Symbols) // 4):
		yield lane.rx_symbol.eq(compose(Symbols[i * 4 : i * 4 + 4]))
		#yield lane.rx_valid.eq(0b1111)
		printl((yield scrambler.rx_symbol))
		val = (yield scrambler.rx_symbol)
		for i in range(4):
			data.append((val >> (10 * i)) & 0x1FF)

		yield
	
	print()

	for i in range(len(Symbols) // 4):
		printl((yield scrambler.rx_symbol))
		val = (yield scrambler.rx_symbol)
		for i in range(4):
			data.append((val >> (10 * i)) & 0x1FF)

		yield

	printl((yield scrambler.rx_symbol))
	val = (yield scrambler.rx_symbol)
	for i in range(4):
		data.append((val >> (10 * i)) & 0x1FF)

	assert data == Reference



sim.add_sync_process(process, domain="rx")

with sim.write_vcd("test.vcd", "test.gtkw"):
	sim.run()