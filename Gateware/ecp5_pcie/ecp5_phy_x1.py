from amaranth import *
from amaranth.build import *
from .ecp5_serdes_geared_x4 import LatticeECP5PCIeSERDESx4
from .ecp5_serdes import LatticeECP5PCIeSERDES
from .serdes import PCIeSERDESAligner, LinkSpeed, Ctrl
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
		self.submodules = [
			self.serdes.lane,
			self.phy
		]
		self.err_cnt_1 = Signal(32)
		self.err_cnt_2 = Signal(32)

		self.state = [self.err_cnt_1, self.err_cnt_2]
		self.state_list = {}

		def make_list(state_list, module, name = ""):
			name = name + module.__class__.__name__ + "."

			for part in module.state:
				assert isinstance(part, Signal) or isinstance(part, Record)
				if isinstance(part, Record):
					def add_record(record, name):
						for field in record.fields:
							if isinstance(record.fields[field], Record):
								add_record(record.fields[field], name + field + ".")
							
							else:
								state_list[name + field] = record.fields[field]
					
					add_record(part, name + part.name + ".")
				
				else:
					state_list[name + part.name] = part
			
			if hasattr(module, "submodules"):
				for submodule in module.submodules:
					make_list(state_list, submodule, name)
		
		make_list(self.state_list, self, "")

	def elaborate(self, platform: Platform) -> Module:
		m = Module()

		m.submodules.serdes = serdes = self.serdes
		m.submodules.aligner = self.aligner
		m.submodules.phy = self.phy

		with m.If(self.phy.ltssm.debug_state > 2):
			with m.If(~serdes.lane.rx_locked):
				m.d.rx += self.err_cnt_1.eq(self.err_cnt_1 + 1)

			with m.If((serdes.lane.rx_symbol[0:9] == Ctrl.Error) | (serdes.lane.rx_symbol[9:18] == Ctrl.Error) | (serdes.lane.rx_symbol[18:27] == Ctrl.Error) | (serdes.lane.rx_symbol[27:36] == Ctrl.Error)):
				m.d.rx += self.err_cnt_2.eq(self.err_cnt_2 + 1)

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