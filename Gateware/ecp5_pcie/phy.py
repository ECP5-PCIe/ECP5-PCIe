from amaranth import *
from amaranth.build import *
from .serdes import K, D, Ctrl, PCIeScrambler
from .phy_rx import PCIePhyRX
from .phy_tx import PCIePhyTX
from .ltssm import PCIeLTSSM
from .dll_tlp import PCIeDLLTLPTransmitter, PCIeDLLTLPReceiver
from .dllp import PCIeDLLPTransmitter, PCIeDLLPReceiver
from .dll import PCIeDLL
from .virtual_tlp_gen import PCIeVirtualTLPGenerator

class PCIePhy(Elaboratable):
    """
    A PCIe Phy
    """
    def __init__(self, lane, upstream = True, disable_scrambling = False):
        # PHY
        self.descrambled_lane = PCIeScrambler(lane)#, Signal())
        self.rx = PCIePhyRX(lane, self.descrambled_lane, 16)
        self.tx = PCIePhyTX(self.descrambled_lane, 16)
        self.ltssm = PCIeLTSSM(self.descrambled_lane, self.tx, self.rx, upstream=upstream, disable_scrambling=disable_scrambling) # It doesn't care whether the lane is scrambled or not, since it only uses it for RX detection in Detect
        
        # DLL
        self.dllp_rx = PCIeDLLPReceiver()
        self.dllp_tx = PCIeDLLPTransmitter()

        self.dll = PCIeDLL(self.ltssm, self.dllp_tx, self.dllp_rx, lane.frequency, use_speed = self.descrambled_lane.use_speed)

        self.dll_tlp_tx = PCIeDLLTLPTransmitter(self.dll)
        self.dll_tlp_rx = PCIeDLLTLPReceiver(self.dll)

        # TL
        self.virt_tlp_gen = PCIeVirtualTLPGenerator()

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        #m.submodules += [
        #    self.rx,
        #    self.tx,
        #    self.descrambled_lane,
        #    self.ltssm,
        #    self.dllp_rx,
        #    self.dllp_tx,
        #    self.dll,
        #    self.dll_tlp_tx,
        #    self.virt_tlp_gen,
        #]
        m.submodules.rx = self.rx
        m.submodules.tx = self.tx
        m.submodules.descrambled_lane = self.descrambled_lane
        m.submodules.ltssm = self.ltssm
        m.submodules.dllp_rx = self.dllp_rx
        m.submodules.dllp_tx = self.dllp_tx
        m.submodules.dll = self.dll
        m.submodules.dll_tlp_tx = self.dll_tlp_tx
        m.submodules.dll_tlp_rx = self.dll_tlp_rx
        m.submodules.virt_tlp_gen = self.virt_tlp_gen

        m.d.comb += self.dll.speed.eq(self.descrambled_lane.speed)

        self.dllp_tx.phy_source.connect(self.tx.sink, m.d.comb)
        self.rx.source.connect(self.dllp_rx.phy_sink, m.d.comb)

        self.dll_tlp_tx.dllp_source.connect(self.dllp_tx.dllp_sink, m.d.comb)

        self.virt_tlp_gen.tlp_source.connect(self.dll_tlp_tx.tlp_sink, m.d.comb)

        self.dllp_rx.dllp_source.connect(self.dll_tlp_rx.dllp_sink, m.d.comb)

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

        m.d.rx += self.descrambled_lane.enable.eq(self.ltssm.status.link.scrambling & ~self.tx.sending_ts)

        return m