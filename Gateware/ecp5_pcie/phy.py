from nmigen import *
from nmigen.build import *
from .serdes import K, D, Ctrl, PCIeScrambler
from .phy_rx import PCIePhyRX
from .phy_tx import PCIePhyTX
from .ltssm import PCIeLTSSM

class PCIePhy(Elaboratable):
    """
    A PCIe Phy
    """
    def __init__(self, lane):
        self.descrambled_lane = PCIeScrambler(lane)
        self.rx = PCIePhyRX(lane, self.descrambled_lane)
        self.tx = PCIePhyTX(self.descrambled_lane)
        self.ltssm = PCIeLTSSM(self.descrambled_lane, self.tx, self.rx) # It doesn't care whether the lane is scrambled or not, since it only uses it for RX detection in Detect

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        m.submodules += [
            self.rx,
            self.tx,
            self.descrambled_lane,
            self.ltssm,
        ]

        m.d.rx += self.descrambled_lane.rx_align.eq(1)

        m.d.rx += self.descrambled_lane.enable.eq(
            self.ltssm.status.link.scrambling & ~self.tx.sending_ts)

        return m