from nmigen import *
from nmigen.build import *
from serdes import K, D, Ctrl, PCIeSERDESInterface
from layouts import ltssm_layout
from phy_tx import PCIePhyTX
from phy_rx import PCIePhyRX
from enum import Enum

class State(Enum):
    Detect = 0
    Detect_Quiet = 0
    Detect_Active = 1
    Polling_Active = 2
    Polling_Active_TS = 3
    Polling_Configuration = 4
    Polling_Configuration_TS = 5
    Configuration_Linkwidth_Start = 6
    Configuration_Linkwidth_Accept = 7
    Configuration_Lanenum_Start = 8
    Configuration_Lanenum_Accept = 9
    Configuration_Complete = 10
    Configuration_Complete_TS = 11
    Configuration_Idle = 12
    Recovery_RcvrLock = 13
    Recovery_RcvrCfg = 14
    Recovery_Idle = 15
    L0 = 16

class PCIeLTSSM(Elaboratable): # Based on Yumewatary phy.py
    """
    PCIe Link Training and Status State Machine for 1:2 gearing

    Parameters
    ----------
    lane : PCIeSERDESInterface
        PCIe lane
    """
    def __init__(self, lane : PCIeSERDESInterface, tx : PCIePhyTX, rx : PCIePhyRX):
        assert lane.ratio == 2
        self.lane = lane
        self.status = Record(ltssm_layout)
        self.tx = tx
        self.rx = rx
        self.debug_state = Signal(8)
        self.rx_ts_count = Signal(range(16 + 1))
        self.tx_ts_count = Signal(range(1024 + 1))

    def elaborate(self, platform: Platform) -> Module: # TODO: Think about clock domains! (assuming RX, TX pll lock, the discrepancy is 0 on average)
        m = Module()

        lane = self.lane
        status = self.status
        clocks_per_ms = 125000 # TODO: Make this non hard coded maybe
        #timer = Signal(range(64 * clocks_per_ms + 1))

        # Number of Training Sequences received, usage depends on FSM state
        rx_ts_count = self.rx_ts_count
        tx_ts_count = self.tx_ts_count

        # Counter for number of IDLE symbols received
        rx_idl_count = Signal(range(4 + 1))
        tx_idl_count = Signal(range(8 + 1))

        # Turn class variables to local variables, for easier code writing
        tx = self.tx
        rx = self.rx

        # Current FSM state, for debugging
        debug_state = self.debug_state

        # Currently its Gen 1 only
        m.d.comb += tx.ts.rate.gen1.eq(1)


        # 
        def timeout(time_in_ms, next_state, or_conds=0):
            """
            Goes to the next state after a specified amount of time has passed

            Parameters:
                time_in_ms: int
                    Time in milliseconds to wait
                next_state:
                    Next state of the FSM to go to
                or_conds:
                    Other conditions which skip the timer
            
            Returns: Signal
                Timer Signal in case it needs to be changed or reset
            """

            # Declare a sufficiently large timer with the reset value being the time
            timer = Signal(range(time_in_ms * clocks_per_ms + 1), reset=time_in_ms * clocks_per_ms)
            m.d.rx += timer.eq(timer - 1)       # Count down until
            with m.If((timer == 0) | or_conds): # t=0 or or_conds is true,
                m.next = next_state             # jump to the next state
            return timer


        # Link Training and Status State Machine, Page 177 in PCIe 1.1, Page 244 in PCIe 3.0
        with m.FSM(domain="rx"): # Page 249 onwards
            with m.State(State.Detect_Quiet): # Change to 2.5 GT/s
                m.d.rx += debug_state.eq(State.Detect_Quiet) # Debug State is 0, with each further state it increases by one
                m.d.rx += status.link.up.eq(0) # Link is down
                m.d.tx += tx.eidle.eq(0b11) # Set the transmitter to send electrical idle
                timeout(12, State.Detect_Active, lane.rx_present) # After 12 ms go to Detect.Active


            with m.State(State.Detect_Active):
                m.d.rx += debug_state.eq(State.Detect_Active)
                m.d.tx += lane.det_enable.eq(1)         # Enable lane detection
                with m.If(lane.det_valid):              # Wait until the detection result is there
                    m.d.tx += lane.det_enable.eq(0)     # And disable lane detection again
                    with m.If(lane.det_status):         # If a lane was detected,
                        m.next = State.Polling_Active   # go to Polling.Active
                    with m.Else():                      # Otherwise
                        m.next = State.Detect           # go back to Detect.
            

            with m.State(State.Polling_Active):
                m.d.rx += debug_state.eq(State.Polling_Active)
                m.d.tx += [
                    tx.ts.valid.eq(1), # Send TS1 ordered sets with Link and Lane set to PAD
                    tx.ts.ts_id.eq(0),
                    tx.ts.link.valid.eq(0),
                    tx.ts.lane.valid.eq(0),
                    tx_ts_count.eq(0),
                ]
                m.d.rx += rx_ts_count.eq(0)
                m.next = State.Polling_Active_TS

                
            with m.State(State.Polling_Active_TS):
                m.d.rx += debug_state.eq(State.Polling_Active_TS)
                with m.If(tx.start_send_ts & (tx_ts_count < 1024)):
                    m.d.tx += tx_ts_count.eq(tx_ts_count + 1)
                with m.If(tx_ts_count >= 1024):
                    with m.If(rx.ts_received):
                        # Accept TS1 Link=PAD Lane=PAD Compliance=0
                        # Accept TS1 Link=PAD Lane=PAD Loopback=1
                        # Accept TS2 Link=PAD Lane=PAD
                        with m.If(rx.ts.valid & ~rx.ts.lane.valid & ~rx.ts.link.valid & 
                        (((rx.ts.ts_id == 0) & ~rx.ts.ctrl.compliance_receive)
                        | ((rx.ts.ts_id == 0) & rx.ts.ctrl.loopback)
                        | (rx.ts.ts_id == 1))):
                            m.d.rx += rx_ts_count.eq(rx_ts_count + 1)
                            with m.If(rx_ts_count == 8):
                                m.next = State.Polling_Configuration
                        with m.Else():
                            m.d.rx += rx_ts_count.eq(0)
                timeout(24, State.Detect)


            with m.State(State.Polling_Configuration):
                m.d.rx += debug_state.eq(State.Polling_Configuration)
                m.next = State.Polling_Configuration_TS
                m.d.tx += [
                    tx.ts.valid.eq(1), # Send TS2 ordered sets with Link and Lane set to PAD
                    tx.ts.ts_id.eq(1),
                    tx.ts.link.valid.eq(0),
                    tx.ts.lane.valid.eq(0),
                    tx_ts_count.eq(0),
                ]
                m.d.rx += rx_ts_count.eq(0)


            with m.State(State.Polling_Configuration_TS):
                m.d.rx += debug_state.eq(State.Polling_Configuration_TS)
                timeout(48, State.Detect)
                with m.If(tx.start_send_ts):
                    with m.If(rx_ts_count == 0):
                        m.d.tx += tx_ts_count.eq(0)
                    with m.Else():
                        m.d.tx += tx_ts_count.eq(tx_ts_count + 1)
                with m.If(rx.ts_received):
                    with m.If(rx.ts.valid & (rx.ts.ts_id == 1) & ~rx.ts.link.valid & ~rx.ts.lane.valid): # Accept TS2 Link=PAD Lane=PAD
                        with m.If(rx_ts_count == 8):
                            with m.If(tx_ts_count >= 16):
                                m.next = State.Configuration_Linkwidth_Start
                        with m.Else():
                            m.d.rx += rx_ts_count.eq(rx_ts_count + 1)
                    with m.Else():
                        m.d.rx += rx_ts_count.eq(0)


            with m.State(State.Configuration_Linkwidth_Start):
                m.d.rx += debug_state.eq(State.Configuration_Linkwidth_Start)
                m.d.tx += [
                    tx.ts.valid.eq(1), # Send TS1 ordered sets with Link and Lane set to PAD
                    tx.ts.ts_id.eq(0),
                    tx.ts.link.valid.eq(0),
                    tx.ts.lane.valid.eq(0),
                ]
                with m.If(rx.ts.valid & (rx.ts.ts_id == 0) & rx.ts.link.valid & ~rx.ts.lane.valid): # Accept TS1 Link=Upstream-Link Lane=PAD
                    m.d.tx += tx.ts.link.valid.eq(1)
                    m.d.tx += tx.ts.link.number.eq(rx.ts.link.number)
                    m.next = State.Configuration_Linkwidth_Accept
                timeout(24, State.Detect)


            with m.State(State.Configuration_Linkwidth_Accept):
                m.d.rx += debug_state.eq(State.Configuration_Linkwidth_Accept)
                # Accept TS1 Link=Upstream-Link Lane=Upstream-Lane
                with m.If(rx.ts.valid & (rx.ts.ts_id == 0) & rx.ts.link.valid & rx.ts.lane.valid):
                    with m.If(rx.ts.lane.number == 0): # Accept lane number 0, in a x4 implementation it should depend on the lane
                        m.d.tx += tx.ts.lane.valid.eq(1)
                        m.d.tx += tx.ts.lane.number.eq(rx.ts.lane.number)
                        m.next = State.Configuration_Lanenum_Wait
                # Accept TS1 Link=PAD Lane=PAD
                timeout(2, State.Detect, (rx.ts.valid & (rx.ts.ts_id == 0) & ~rx.ts.link.valid & ~rx.ts.lane.valid))


            with m.State(State.Configuration_Lanenum_Wait):
                m.d.rx += debug_state.eq(State.Configuration_Lanenum_Wait)
                # Accept TS1 Link=Upstream-Link Lane=Upstream-Lane
                with m.If(rx.ts.valid & (rx.ts.ts_id == 0) & rx.ts.link.valid & rx.ts.lane.valid):
                    with m.If(rx.ts.lane.number != tx.ts.lane.number):
                        m.next = State.Configuration_Lanenum_Accep
                # Accept TS2
                with m.If(rx.ts.valid & (rx.ts.ts_id == 1)):
                    m.next = State.Configuration_Lanenum_Accep
                # Accept TS1 Link=PAD Lane=PAD
                timeout(2, State.Detect, (rx.ts.valid & (rx.ts.ts_id == 0) & ~rx.ts.link.valid & ~rx.ts.lane.valid))


            with m.State(State.Configuration_Lanenum_Accep):
                m.d.rx += debug_state.eq(State.Configuration_Lanenum_Accep)
                # Accept TS2 Link=Upstream-Link Lane=Upstream-Lane
                with m.If(rx.ts.valid & (rx.ts.ts_id == 1) & rx.ts.link.valid & rx.ts.lane.valid):
                    with m.If((rx.ts.link.number == tx.ts.link.number) & (rx.ts.lane.number == tx.ts.lane.number)):
                        m.next = State.Configuration_Complete
                    with m.Else():
                        m.next = State.Detect
                with m.If(rx.ts.valid & (rx.ts.ts_id == 0) & ~rx.ts.link.valid & ~rx.ts.lane.valid):
                    m.next = State.Detect


            with m.State(State.Configuration_Complete):
                m.d.rx += debug_state.eq(State.Configuration_Complete)
                m.d.tx += [
                    tx.ts.ts_id.eq(1),
                    tx.ts.n_fts.eq(0xFF),
                    tx_ts_count.eq(0)
                ]
                m.d.rx += rx_ts_count.eq(0)
                m.next = State.Configuration_Complete_TS


            with m.State(State.Configuration_Complete_TS):
                m.d.rx += debug_state.eq(State.Configuration_Complete_TS)
                with m.If(tx.start_send_ts):
                    with m.If(rx_ts_count == 0):
                        m.d.tx += tx_ts_count.eq(0)
                    with m.Else():
                        m.d.tx += tx_ts_count.eq(tx_ts_count + 1)
                with m.If(rx.ts_received):
                    # Accept TS2 Link=Upstream-Link Lane=Upstream-Lane
                    with m.If(rx.ts.valid & (rx.ts.ts_id == 1) & rx.ts.link.valid & rx.ts.lane.valid &
                        (rx.ts.link.number == tx.ts.link.number) &
                        (rx.ts.lane.number == tx.ts.lane.number)):
                        with m.If(rx_ts_count == 8):
                            with m.If(tx_ts_count == 16):
                                m.next = State.Configuration_Idle
                        with m.Else():
                            m.d.rx += rx_ts_count.eq(rx_ts_count + 1)
                    with m.Else():
                        m.d.rx += rx_ts_count.eq(0)
                timeout(2, State.Detect)


            with m.State(State.Configuration_Idle):
                m.d.rx += debug_statee.eq(State.Configuration_Idle)
                m.d.tx += tx.ts.valid.eq(0)
                m.d.tx += tx.idle.eq(1)
                m.d.tx += tx_ts_count.eq(0)
                m.d.rx += rx_ts_count.eq(0)
                with m.If(lane.rx_symbol == Cat(Ctrl.IDL, Ctrl.IDL)):
                    with m.If(rx_idl_count < 4):
                        m.d.rx += rx_idl_count.eq(rx_idl_count + 1)
                        m.d.tx += tx_idl_count.eq(0)
                    with m.Else():
                        m.d.tx += tx_idl_count.eq(tx_idl_count + 1)
                        with m.If(tx_idl_count >= 8):
                            m.d.tx += tx.idle.eq(0)
                            m.next = State.L0
                with m.Else():
                    m.d.rx += rx_idl_count.eq(0)
                #m.d.tx += lane.tx_symbol.eq(Cat(Ctrl.IDL, Ctrl.IDL))
                m.d.rx += status.link.up.eq(1)
                timer = Signal(range(2 * clocks_per_ms + 1), reset = 2 * clocks_per_ms)
                m.d.rx += timer.eq(timer - 1)
                with m.If(timer == 0):
                    m.d.tx += tx.idle.eq(0)
                    with m.If(status.idle_to_rlock_transitioned < 0xFF): # Set to 0xFF on transition to Recovery.RcvrLock
                        m.next = State.Recovery_RcvrLock
                    with m.Else():
                        m.next = State.Detect

                        
            with m.State(State.Recovery_RcvrLock):
                m.d.rx += debug_state.eq(State.Recovery_RcvrLock)
                m.d.tx += [
                    tx.ts.valid.eq(1), # Send TS1 ordered sets with same Link and Lane as configured
                    tx.ts.ts_id.eq(0)
                ]
                with m.If(rx.ts_received & rx.ts.valid & rx.ts.link.valid & rx.ts.lane.valid &
                    (rx.ts.link.number == tx.ts.link.number) &
                    (rx.ts.lane.number == tx.ts.lane.number)):
                    m.d.rx += rx_ts_count.eq(rx_ts_count + 1)
                with m.If(rx_ts_count == 8):
                    m.d.rx += rx_ts_count.eq(0)
                    m.next = State.Recovery_RcvrCfg
                with m.If(~rx.recv_tsn): # Not consecutive, check if this works
                    m.d.rx += rx_ts_count.eq(0)
                timeout(24, State.Detect)


            with m.State(State.Recovery_RcvrCfg): # Revise when implementing 5 GT/s, page 290
                m.d.rx += debug_state.eq(State.Recovery_RcvrCfg)
                m.d.tx += [
                    tx.ts.valid.eq(1), # Send TS2 ordered sets with same Link and Lane as configured
                    tx.ts.ts_id.eq(1)
                ]
                last_ts = Signal()
                m.d.rx += last_ts.eq(rx.ts.ts_id)
                rx_recvd = Signal()
                m.d.rx += rx_recvd.eq(rx_recvd | rx.ts_received)
                with m.If(tx.start_send_ts):
                    m.d.tx += tx_ts_count.eq(tx_ts_count + 1)
                with m.If(last_ts != rx.ts.ts_id):
                    m.d.rx += rx_ts_count.eq(0)
                with m.If(rx.ts_received & (rx.ts.ts_id == 1) & rx.ts.valid & rx.ts.link.valid & rx.ts.lane.valid & (rx.ts.rate.speed_change == 0) &
                    (rx.ts.link.number == tx.ts.link.number) &
                    (rx.ts.lane.number == tx.ts.lane.number)):
                    with m.If(rx.ts.rate.speed_change == 0):
                        m.d.rx += rx_ts_count.eq(rx_ts_count + 1)
                    with m.Else():
                        m.d.rx += rx_ts_count.eq(0)
                with m.If((rx_ts_count == 8) & (last_ts == 1)):
                    m.next = State.Recovery_Idle
                with m.If((rx_ts_count == 8) & (last_ts == 0) & (tx_ts_count == 16) & (rx.ts.rate.speed_change == 0)):
                    m.next = State.Configuration_Linkwidth_Start
                timeout(48, State.Detect)


            with m.State(State.Recovery_Idle):
                m.d.rx += debug_state.eq(State.Recovery_Idle)
                pad_cnt = Signal(1)
                with m.If(~rx.ts.lane.valid):
                    with m.If(~pad_cnt):
                        m.d.rx += pad_cnt.eq(1)
                    with m.Else():
                        m.next = State.Configuration_Linkwidth_Start
                m.d.tx += tx.idle.eq(1)
                with m.If(lane.rx_symbol == Cat(Ctrl.IDL, Ctrl.IDL)):
                    with m.If(rx_idl_count < 4):
                        m.d.rx += rx_idl_count.eq(rx_idl_count + 1)
                        m.d.tx += tx_idl_count.eq(0)
                    with m.Else():
                        m.d.tx += tx_idl_count.eq(tx_idl_count + 1)
                        with m.If(tx_idl_count >= 8):
                            m.d.rx += status.idle_to_rlock_transitioned.eq(0)
                            m.d.tx += tx.idle.eq(0)
                            m.next = State.L0
                with m.Else():
                    m.d.rx += rx_idl_count.eq(0)
                timer = Signal(range(2 * clocks_per_ms + 1), reset = 2 * clocks_per_ms)
                m.d.rx += timer.eq(timer - 1)
                with m.If(timer == 0):
                    m.d.tx += tx.idle.eq(0)
                    with m.If(status.idle_to_rlock_transitioned < 0xFF):
                        m.next = State.Recovery_RcvrLock
                    with m.Else():
                        m.next = State.Detect


            with m.State(State.L0): # Page 297, implementation for 5 GT/s and higher lane counts missing
                m.d.rx += debug_state.eq(State.L0)
                m.d.rx += status.link.up.eq(1)
                with m.If(lane.rx_has_symbol(Ctrl.STP) | lane.rx_has_symbol(Ctrl.SDP)):
                    m.d.rx += status.idle_to_rlock_transitioned.eq(0)

                    
        return m