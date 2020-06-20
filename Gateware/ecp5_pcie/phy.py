from nmigen import *
from nmigen.build import *
from .serdes import K, D, Ctrl, PCIeSERDESInterface

class PCIePhy():
    """
    A PCIe Phy
    """
    def __init__(self, lane):
        pass
    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        return m