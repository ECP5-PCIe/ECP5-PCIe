from nmigen import *
from nmigen.build import *
from .ecp5_serdes_geared_x2 import LatticeECP5PCIeSERDESx2
from .ecp5_serdes import LatticeECP5PCIeSERDES
from .serdes import PCIeSERDESAligner
from .phy import PCIePhy

class LatticeECP5PCIePhy(Elaboratable):
    """
    A PCIe Phy for the ECP5 for PCIe Gen1 x1
    """
    def __init__(self):
        #self.__serdes = LatticeECP5PCIeSERDESx2() # Declare SERDES module with 1:2 gearing
        self.__serdes = LatticeECP5PCIeSERDES(2) # Declare SERDES module with 1:2 gearing
        self.__aligner = DomainRenamer("rx")(PCIeSERDESAligner(self.__serdes.lane)) # Aligner for aligning COM symbols
        self.phy = PCIePhy(self.__aligner)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        m.submodules.serdes = serdes = self.__serdes
        m.submodules.aligner = self.__aligner
        m.submodules.phy = self.phy
        
        m.domains.rx = ClockDomain()
        m.domains.tx = ClockDomain()
        m.d.comb += [
            ClockSignal("rx").eq(serdes.rx_clk),
            ClockSignal("tx").eq(serdes.tx_clk),
        ]

        return m