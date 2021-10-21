from nmigen import *
from nmigen.build import *
from enum import IntEnum

from .ltssm import PCIeLTSSM
from .serdes import K, D, Ctrl
from .layouts import dll_layout
from .dllp import PCIeDLLPTransmitter, PCIeDLLPReceiver, DLLPType

class State(IntEnum):
    DL_Inactive = 0
    DL_Init_FC1 = 1
    DL_Init_FC2 = 2
    DL_Active = 3

class FCType(IntEnum):
    FC1 = 1
    FC2 = 3
    UpdateFC = 2

#
# This implements the PCIe Data Link Layer
#

class PCIeDLL(Elaboratable): # Based on Yumewatary phy.py
    """
    PCIe Data Link Layer

    Parameters
    ----------
    clk_freq : int
        Maximum clock frequency in Hz, the speed in 5 GT/s mode
    up : Signal()
        Whether the DLL is active
    credits_tx : Record(dll_layout)
        Credits to transmit
    credits_rx : Record(dll_layout)
        Received credits
    speed : Signal()
        Speed, from LinkSpeed enum from serdes.py
    """
    def __init__(self, ltssm : PCIeLTSSM, tx : PCIeDLLPTransmitter, rx : PCIeDLLPReceiver, clk_freq : int):
        self.up = Signal()
        self.ltssm = ltssm
        self.tx = tx
        self.rx = rx
        self.credits_tx = Record(dll_layout)
        self.credits_rx = Record(dll_layout)
        self.clk_freq = clk_freq
        self.speed = Signal()

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        # Which DLLPs have arrived
        got_p = Signal()
        got_np = Signal()
        got_cpl = Signal()

        m.d.comb += [ # Fix this maybe
            self.credits_tx.PH.eq(128),
            self.credits_tx.PD.eq(2048),
            self.credits_tx.NPH.eq(128),
            self.credits_tx.NPD.eq(128),
            self.credits_tx.CPLH.eq(0), # Must advertise infinite as root complex or endpoint
            self.credits_tx.CPLD.eq(0), #
        ]

        # Which DLLPs to transmit, only concerning Flow Control Initialization
        fc_type = Signal(2)
        transmit_dllps = Signal()
        done_dllp_transmission = Signal()

        # For later use
        sending_tlp = Signal() # TODO: Connect this wire for proper operation

        # Get update DLLPs
        with m.If(~self.ltssm.status.link.up):
            pass
        with m.Elif(self.rx.dllp.valid & (self.rx.dllp.type == DLLPType.UpdateFC_P)):
            m.d.rx += self.credits_rx.PH.eq(self.rx.dllp.header)
            m.d.rx += self.credits_rx.PD.eq(self.rx.dllp.data)
            m.d.rx += got_p.eq(1)
        with m.Elif(self.rx.dllp.valid & (self.rx.dllp.type == DLLPType.UpdateFC_NP)):
            m.d.rx += self.credits_rx.NPH.eq(self.rx.dllp.header)
            m.d.rx += self.credits_rx.NPD.eq(self.rx.dllp.data)
            m.d.rx += got_np.eq(1)
        with m.Elif(self.rx.dllp.valid & (self.rx.dllp.type == DLLPType.UpdateFC_Cpl)):
            m.d.rx += self.credits_rx.CPLH.eq(self.rx.dllp.header)
            m.d.rx += self.credits_rx.CPLD.eq(self.rx.dllp.data)

        # Data Link Layer State Machine, Page 129 in PCIe 1.1
        with m.FSM(domain="rx"):
            with m.State(State.DL_Inactive):
                m.d.rx += [
                    self.up.eq(0),
                    got_p.eq(0),
                    got_np.eq(0),
                    got_cpl.eq(0),
                    done_dllp_transmission.eq(0),
                    transmit_dllps.eq(0),
                ]
                with m.If(self.ltssm.status.link.up): # TODO: link on transaction layer must not be disabled
                    m.next = State.DL_Init_FC1

            # Inconsistent naming of Cpl / CPL taken from specification.
            with m.State(State.DL_Init_FC1):
                with m.If(~self.ltssm.status.link.up):
                    m.next = State.DL_Inactive
                with m.Elif(self.rx.dllp.valid & (self.rx.dllp.type == DLLPType.InitFC1_P)):
                    m.d.rx += self.credits_rx.PH.eq(self.rx.dllp.header)
                    m.d.rx += self.credits_rx.PD.eq(self.rx.dllp.data)
                    m.d.rx += got_p.eq(1)
                with m.Elif(self.rx.dllp.valid & (self.rx.dllp.type == DLLPType.InitFC1_NP)):
                    m.d.rx += self.credits_rx.NPH.eq(self.rx.dllp.header)
                    m.d.rx += self.credits_rx.NPD.eq(self.rx.dllp.data)
                    m.d.rx += got_np.eq(1)
                with m.Elif(self.rx.dllp.valid & (self.rx.dllp.type == DLLPType.InitFC1_Cpl)):
                    m.d.rx += self.credits_rx.CPLH.eq(self.rx.dllp.header)
                    m.d.rx += self.credits_rx.CPLD.eq(self.rx.dllp.data)
                    m.d.rx += got_cpl.eq(1)
                
                m.d.rx += fc_type.eq(FCType.FC1)
                m.d.rx += transmit_dllps.eq(1)
                
                with m.If(got_p & got_np & got_cpl & done_dllp_transmission):
                    m.d.rx += done_dllp_transmission.eq(0)
                    m.d.rx += transmit_dllps.eq(0)
                    m.next = State.DL_Init_FC2

            with m.State(State.DL_Init_FC2):
                m.d.rx += fc_type.eq(FCType.FC2)
                m.d.rx += transmit_dllps.eq(1)
                with m.If(done_dllp_transmission & (self.rx.dllp.type[2:4] == FCType.FC2)):
                    m.d.rx += transmit_dllps.eq(0)
                    m.next = State.DL_Active

            with m.State(State.DL_Active):
                # This is supposed to be in the above state, but does it matter?
                m.d.rx += self.up.eq(1)

                # Send DLLP UpdateFC packets often enough, assumes 125 MHz clock, transmits every 25 µs if there is no other ongoing transmission
                clk = self.clk_freq
                min_delay = 25E-6
                update_timer = Signal(range(int(min_delay * clk + 1)))

                m.d.rx += update_timer.eq(update_timer + 1)
                m.d.rx += transmit_dllps.eq(0)

                with m.If(((update_timer << self.speed) >= int(min_delay * clk)) & ~sending_tlp):
                    m.d.rx += fc_type.eq(FCType.UpdateFC)
                    m.d.rx += transmit_dllps.eq(1)
                    m.d.rx += done_dllp_transmission.eq(0)
                    m.d.rx += update_timer.eq(0)
                #with m.Elif(done_dllp_transmission):
                #    m.d.rx += transmit_dllps.eq(0)
                    
                with m.If(~self.ltssm.status.link.up): # TODO: Why does it cause u-boot on the RP64 to reboot?
                    m.next = State.DL_Inactive
        
        # DLLP sending FSM
        # TODO: It transmits the first packet twice. This doesn't break it but it unnecessarily takes up bandwidth.
        with m.FSM(domain="rx"):
            with m.State("Idle"):
                m.d.rx += self.tx.send.eq(0)
                with m.If(transmit_dllps):
                    m.next = "P"

            # Const(n, 2) means n = 0: P, n = 1: NP, n = 2: CPL
            with m.State("P"):
                #with m.If(~transmit_dllps):
                #    m.d.rx += done_dllp_transmission.eq(0)
                #    m.next = "Idle"

                m.d.rx += [
                    self.tx.dllp.type.eq(Cat(Const(0, 2), fc_type)),
                    self.tx.dllp.header.eq(self.credits_tx.PH),
                    self.tx.dllp.data.eq(self.credits_tx.PD),
                    self.tx.dllp.valid.eq(1),
                    self.tx.send.eq(1),
                ]

                with m.If(self.tx.started_sending):
                    m.d.rx += self.tx.send.eq(0)
                    m.next = "NP"

            with m.State("NP"):
                #with m.If(~transmit_dllps):
                #    m.d.rx += done_dllp_transmission.eq(0)
                #    m.next = "Idle"
                    
                m.d.rx += [
                    self.tx.dllp.type.eq(Cat(Const(1, 2), fc_type)),
                    self.tx.dllp.header.eq(self.credits_tx.NPH),
                    self.tx.dllp.data.eq(self.credits_tx.NPD),
                    self.tx.dllp.valid.eq(1),
                    self.tx.send.eq(1),
                ]
                with m.If(self.tx.started_sending):
                    m.d.rx += self.tx.send.eq(0)
                    m.next = "CPL"

            with m.State("CPL"):
                #with m.If(~transmit_dllps):
                #    m.d.rx += done_dllp_transmission.eq(0)
                #    m.next = "Idle"
                    
                m.d.rx += [
                    self.tx.dllp.type.eq(Cat(Const(2, 2), fc_type)),
                    self.tx.dllp.header.eq(self.credits_tx.CPLH),
                    self.tx.dllp.data.eq(self.credits_tx.CPLD),
                    self.tx.dllp.valid.eq(1),
                    self.tx.send.eq(1),
                ]
                with m.If(self.tx.started_sending):
                    m.d.rx += self.tx.send.eq(0)
                    # This is kind of a hack to ensure that it doesn't toggle to 1 when it isn't supposed to transmit (but still finishing a transmission)
                    m.d.rx += done_dllp_transmission.eq(transmit_dllps)
                    with m.If(transmit_dllps):
                        m.next = "P"
                    with m.Else():
                        m.next = "Idle"

        return m