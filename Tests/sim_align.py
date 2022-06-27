from amaranth import *
from amaranth.build import *
from amaranth.sim import Simulator
from ecp5_pcie.align import SymbolSlip
from ecp5_pcie.serdes import K, D, Ctrl

if __name__ == "__main__":
	m = Module()

	m.submodules.slip = slip = SymbolSlip(symbol_size = 10, word_size = 4, comma = Cat(Const(Ctrl.COM, 9), 1))


	sim = Simulator(m)
	sim.add_clock(1 / 125e6, domain="rx")# For NextPNR, set the maximum clock frequency such that errors are given

	Symbols = [Ctrl.COM, Ctrl.SKP, Ctrl.SKP, Ctrl.SKP,
	           D(0, 0), D(1, 0), D(2, 0), D(3, 0),
	           D(0, 0), D(1, 0), D(2, 0), D(3, 0),
	           D(0, 0), D(1, 0), D(2, 0), D(3, 0),
	           D(0, 0), D(1, 0), D(2, 0), Ctrl.COM,
	           Ctrl.SKP, Ctrl.SKP, Ctrl.SKP, D(3, 0),
	           D(0, 0), D(1, 0), D(2, 0), D(3, 0),
	           D(0, 0), D(1, 0), D(2, 0), D(3, 0),
	           D(0, 0), D(1, 0), D(2, 0), D(3, 0),
	           D(0, 0), D(1, 0), D(2, 0), Ctrl.COM,
	           Ctrl.SKP, Ctrl.SKP, Ctrl.SKP, D(3, 0),
	           D(0, 0), D(1, 0), D(2, 0), D(3, 0),
	           D(0, 0), D(1, 0), D(2, 0), D(3, 0)]

	def process():
		def printl(val):
			for i in range(4):
				sym = (val >> (10 * i)) & 0x1FF
				print(sym, end="\t\t")

			print()

		for cyc in range(len(Symbols) // 4):
			yield slip.i.eq(Cat(
					(Const(Symbols[n + 4 * cyc], 9), 1)
					for n in range(4)
				))
			printl((yield slip.o))
			yield

		for cyc in range(len(Symbols) // 4):
			printl((yield slip.o))
			yield

		printl((yield slip.o))

	sim.add_sync_process(process, domain="rx")

	with sim.write_vcd("test.vcd", "test.gtkw"):
		sim.run()