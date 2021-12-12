from amaranth import *
from amaranth.build import *
from .virtual_serdes import VirtualPCIeSERDESx4
from .ecp5_serdes import LatticeECP5PCIeSERDES
from .serdes import PCIeSERDESAligner, LinkSpeed
from .phy import PCIePhy

class VirtualPCIePhy(Elaboratable):
    """
    A PCIe Phy for the ECP5 for PCIe Gen1 x1
    """
    def __init__(self, upstream = True):
        self.serdes = VirtualPCIeSERDESx4(speed_5GTps=True) # Declare SERDES module with 1:4 gearing
        self.aligner = DomainRenamer({"rx" : "sync", "tx" : "sync"})(PCIeSERDESAligner(self.serdes.lane)) # Aligner for aligning COM symbols
        self.phy = DomainRenamer({"rx" : "sync", "tx" : "sync"})(PCIePhy(self.aligner, upstream=upstream, disable_scrambling=True)) # TODO: This is an inconsistency
        #self.serdes.lane.speed = 1

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        m.submodules.serdes = serdes = self.serdes
        m.submodules.aligner = self.aligner
        m.submodules.phy = self.phy

        m.d.comb += self.serdes.lane.speed.eq(LinkSpeed.S2_5)
        
        #m.domains.rx = ClockDomain()
        #m.domains.tx = ClockDomain()
        #m.d.comb += [
        #    ClockSignal("rx").eq(serdes.rx_clk),
        #    ClockSignal("tx").eq(serdes.tx_clk),
        #]

        return m