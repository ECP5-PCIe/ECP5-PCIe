from nmigen import *
from serdes import K, D, Ctrl, PCIeSERDESInterface

class PCIePhyRX():
    """
    PCIe receiver
    """
    def __init__(self, lane):
        self.lane = lane

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        with m.FSM(domain="rx"):
            

        return m