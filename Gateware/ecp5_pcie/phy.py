from nmigen import *
from nmigen.build import *
from .serdes import K, D, Ctrl, PCIeScrambler
from .phy_rx import PCIePhyRX
from .phy_tx import PCIePhyTX
from .ltssm import PCIeLTSSM
from .dllp import PCIeDLLPTransmitter, PCIeDLLPReceiver
from .dll import PCIeDLL

class PCIePhy(Elaboratable):
    """
    A PCIe Phy
    """
    def __init__(self, lane):
        self.descrambled_lane = PCIeScrambler(lane)
        self.rx = PCIePhyRX(lane, self.descrambled_lane, 16)
        self.tx = PCIePhyTX(self.descrambled_lane, 16)
        self.ltssm = PCIeLTSSM(self.descrambled_lane, self.tx, self.rx) # It doesn't care whether the lane is scrambled or not, since it only uses it for RX detection in Detect
        self.dllp_rx = PCIeDLLPReceiver(self.rx.source)
        self.dllp_tx = PCIeDLLPTransmitter()

        self.dll = PCIeDLL(self.ltssm, self.dllp_tx, self.dllp_rx)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        m.submodules += [
            self.rx,
            self.tx,
            self.descrambled_lane,
            self.ltssm,
            self.dllp_rx,
            self.dllp_tx,
            self.dll,
        ]

        self.dllp_tx.source.connect(self.tx.sink, m.d.comb)

        #m.submodules.dlrx=    self.dllp_rx
        #m.submodules.dltx=    self.dllp_tx
        #m.submodules.dll =    self.dll
        #m.d.comb        +=    self.dllp_tx.enable.eq(self.tx.enable_higher_layers)
        #    self.dllp_tx,


        # TESTING
        
        #m.d.rx += self.dllp_tx.dllp.eq(self.dllp_rx.fifo.r_data)
        #m.d.rx += self.dllp_rx.fifo.r_en.eq(1)
        #m.d.rx += self.tx.fifo.w_en.eq(self.rx.fifo.r_rdy)
        #m.d.rx += self.rx.fifo.r_en.eq(self.rx.fifo.r_rdy)
        #counter = Signal(8)
        #m.d.rx += counter.eq(counter + 1)
        #m.d.rx += self.tx.fifo.w_data.eq(counter)
        #m.d.rx += self.tx.fifo.w_en.eq(counter < 128)




        m.d.rx += self.descrambled_lane.rx_align.eq(1)

        m.d.rx += self.descrambled_lane.enable.eq(
            self.ltssm.status.link.scrambling & ~self.tx.sending_ts)

        return m