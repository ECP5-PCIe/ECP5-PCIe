from nmigen import *
from nmigen.build import *
from serdes import K, D, Ctrl, PCIeSERDESInterface
from layouts import ltssm_layout

class PCIeLTSSM():
    """
    PCIe Link Training and Status State Machine for 1:2 gearing

    Parameters
    ----------
    lane : PCIeSERDESInterface
        PCIe lane
    """
    def __init__(self, lane : PCIeSERDESInterface):
        assert lane.ratio == 2
        self.lane = lane
        self.status = Record(ltssm_layout)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        lane = self.lane
        status = self.status
        clocks_per_ms = 250000 # TODO: Make this non hard coded maybe
        timer = Signal(range(64 * clocks_per_ms + 1))

        with m.FSM(domain="rx"): # Page 249 onwards
            with m.State("Detect.Quiet.Init"): # Change to 2.5 GT/s
                m.d.rx += status.link.up.eq(0)
                m.d.rx += lane.tx_e_idle.eq(0b11)
                m.d.rx += timer.eq(clocks_per_ms * 12)
                m.next = "Detect.Quiet.Timeout"
            with m.State("Detect.Quiet.Timeout"):
                m.d.rx += timer.eq(timer - 1)
                with m.If(lane.rx_present | (timer == 0)):
                    m.d.rx += lane.det_enable.eq(1)
                    m.next = "Detect.Active"
            with m.State("Detect.Active"):
                with m.If(lane.det_valid):
                    m.d.rx += lane.det_enable.eq(0)
                    with m.If(lane.det_status):
                        m.next = "Polling.Active"
                    with m.Else():
                        m.next = "Detect.Quiet"
        return m