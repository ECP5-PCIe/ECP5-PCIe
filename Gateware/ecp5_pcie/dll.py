from nmigen import *
from nmigen.build import *

from enum import IntEnum
from .ltssm import PCIeLTSSM

from .serdes import K, D, Ctrl

class State(IntEnum):
    DL_Inactive = 0
    DL_Init = 1
    DL_Active = 2

class PCIeDLL(Elaboratable): # Based on Yumewatary phy.py
    """
    PCIe Data Link Layer
    """
    def __init__(self, ltssm : PCIeLTSSM):
        self.up = Signal()
        self.ltssm = ltssm

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        # Data Link Layer State Machine, Page 129 in PCIe 1.1
        with m.FSM(domain="rx"):
            with m.State(State.DL_Inactive):
                m.d.rx += up.eq(0)
                with m.If(self.ltssm.status.link.up): # TODO: link on transaction layer must not be disabled
                    m.next = State.DL_Init

            with m.State(State.DL_Init):
                with m.If(~self.ltssm.status.link.up):
                    m.next = State.DL_Inactive


            with m.State(State.DL_Active):
                pass
                

        return m