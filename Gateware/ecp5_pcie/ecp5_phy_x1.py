from amaranth import *
from amaranth.build import *
from .ecp5_serdes_geared_x4 import LatticeECP5PCIeSERDESx4
from .ecp5_serdes import LatticeECP5PCIeSERDES
from .serdes import PCIeSERDESAligner, LinkSpeed
from .phy import PCIePhy
from .ltssm import State

class LatticeECP5PCIePhy(Elaboratable):
	"""
	A PCIe Phy for the ECP5 for PCIe x1
	"""
	def __init__(self, support_5GTps = True):
		#self.__serdes = LatticeECP5PCIeSERDESx2() # Declare SERDES module with 1:2 gearing
		self.serdes = LatticeECP5PCIeSERDESx4(speed_5GTps=support_5GTps, clkfreq=100e6, fabric_clk=True) # Declare SERDES module with 1:4 gearing
		self.aligner = DomainRenamer("rx")(PCIeSERDESAligner(self.serdes.lane)) # Aligner for aligning COM symbols
		self.phy = PCIePhy(self.aligner, support_5GTps=support_5GTps)
		#self.serdes.lane.speed = 1

	def elaborate(self, platform: Platform) -> Module:
		m = Module()

		m.submodules.serdes = serdes = self.serdes
		m.submodules.aligner = self.aligner
		m.submodules.phy = self.phy

		m.d.comb += self.serdes.lane.speed.eq(LinkSpeed.S2_5)
		
		m.domains.rx = ClockDomain()
		m.domains.tx = ClockDomain()
		m.d.comb += [
			ClockSignal("rx").eq(serdes.rx_clk),
			ClockSignal("tx").eq(serdes.tx_clk),
		]

		last_state = Signal(8)
		m.d.rx += last_state.eq(self.phy.ltssm.debug_state)
		with m.If((last_state == State.L0) & (self.phy.ltssm.debug_state == State.Detect)):
			m.d.comb += ResetSignal("rx").eq(1)

		return m