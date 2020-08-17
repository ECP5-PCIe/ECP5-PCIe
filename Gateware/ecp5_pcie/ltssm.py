from nmigen import *
from nmigen.build import *

from enum import IntEnum

from .serdes import K, D, Ctrl, PCIeSERDESInterface
from .layouts import ltssm_layout
from .phy_tx import PCIePhyTX
from .phy_rx import PCIePhyRX

class State(IntEnum):
    Detect_Quiet = 0
    Detect = 0
    Detect_Active = 1
    Polling_Active = 2
    Polling = 2
    Polling_Active_TS = 3
    Polling_Configuration = 4
    Polling_Configuration_TS = 5
    Configuration_Linkwidth_Start = 6
    Configuration = 6
    Configuration_Linkwidth_Accept = 7
    Configuration_Lanenum_Start = 8
    Configuration_Lanenum_Wait = 9
    Configuration_Lanenum_Accept = 10
    Configuration_Complete = 11
    Configuration_Complete_TS = 12
    Configuration_Idle = 13
    Recovery_RcvrLock = 14
    Recovery = 14
    Recovery_RcvrCfg = 15
    Recovery_Idle = 16
    L0 = 17

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

        # Debug
        self.debug_state = Signal(8)
        self.rx_ts_count = Signal(range(16 + 1))
        self.tx_ts_count = Signal(range(1024 + 1))
        self.rx_idl_count_total = Signal(32)

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

        # TODO: Add scrambling
        m.d.comb += tx.ts.ctrl.disable_scrambling.eq(1)

        #Debugging stuff
        with m.If(lane.rx_symbol == Cat(Ctrl.IDL, Ctrl.IDL)):
            m.d.rx += self.rx_idl_count_total.eq(self.rx_idl_count_total + 2)
        with m.Elif(lane.rx_symbol[0:9] == Ctrl.IDL):
            m.d.rx += self.rx_idl_count_total.eq(self.rx_idl_count_total + 1)
        with m.Elif(lane.rx_symbol[9:18] == Ctrl.IDL):
            m.d.rx += self.rx_idl_count_total.eq(self.rx_idl_count_total + 1)
        
        m.d.rx += tx.ts.ctrl.loopback.eq(0)

        
        def reset_ts_count_and_jump(next_state):
            """
            Goes to the next state and resets the TS counters

            Parameters:
                next_state:
                    Next state of the FSM to go to
            """
            m.d.rx += rx_ts_count.eq(0)
            m.d.rx += tx_ts_count.eq(0)
            m.d.rx += timer.eq(0)
            m.next = next_state


        # Timer for the timeout function
        timer = Signal(range(64 * clocks_per_ms + 1))

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

            # Count down until t=0 or or_conds is true, then jump to the next state
            m.d.rx += timer.eq(timer + 1)
            with m.If((timer == time_in_ms * clocks_per_ms) | or_conds):
                m.d.rx += timer.eq(0)
                reset_ts_count_and_jump(next_state)
            return timer


        # Link Training and Status State Machine, Page 177 in PCIe 1.1, Page 244 in PCIe 3.0
        with m.FSM(domain="rx"): # Page 249 onwards
            with m.State(State.Detect_Quiet): # Change to 2.5 GT/s
                m.d.rx += debug_state.eq(State.Detect_Quiet) # Debug State is there to find out which state the FSM is in

                # The Link is now down and the TX SERDES is put into electrical idle
                m.d.rx += status.link.up.eq(0)
                m.d.rx += tx.eidle.eq(0b11)

                # After 12 milliseconds are over or a signal is present on the receive side, go to Detect.Active
                # And wait a few cycles
                timeout(12, State.Detect_Active, lane.rx_present & (timer > 20)) # ~rx_present_last & 


            with m.State(State.Detect_Active): # Revise spec section 4.2.6.1.2 for the case of multiple lanes
                m.d.rx += debug_state.eq(State.Detect_Active)
                # Enable lane detection
                m.d.rx += lane.det_enable.eq(1)
                m.d.rx += tx.eidle.eq(0)

                with m.If(lane.det_valid):
                    # Wait until the detection result is there and disable lane detection again as soon as it is.
                    m.d.rx += lane.det_enable.eq(0)
                    #  If a lane was detected, go to Polling.Active otherwise go back to Detect.
                    with m.If(lane.det_status): # (Note: currently hardwired to 1 in ecp5_serdes.py)
                        reset_ts_count_and_jump(State.Polling)
                    with m.Else():
                        reset_ts_count_and_jump(State.Detect_Quiet)
            

            with m.State(State.Polling_Active):
                m.d.rx += debug_state.eq(State.Polling_Active)

                # Send TS1 ordered sets with Link and Lane set to PAD
                m.d.rx += [
                    tx.ts.valid.eq(1),
                    tx.ts.ts_id.eq(0),
                    tx.ts.link.valid.eq(0),
                    tx.ts.lane.valid.eq(0),
                    tx_ts_count.eq(0),
                ]
                m.d.rx += rx_ts_count.eq(0)
                reset_ts_count_and_jump(State.Polling_Active_TS)

                
            with m.State(State.Polling_Active_TS):
                m.d.rx += debug_state.eq(State.Polling_Active_TS)

                # Count for 1024 transmitted TS's
                with m.If(tx.start_send_ts & (tx_ts_count < 1024)):
                    m.d.rx += tx_ts_count.eq(tx_ts_count + 1)
                
                with m.If(rx.ts_received):
                    # Accept TS1 Link=PAD Lane=PAD Compliance=0
                    # Accept TS1 Link=PAD Lane=PAD Loopback=1
                    # Accept TS2 Link=PAD Lane=PAD
                    with m.If(rx.ts.valid & ~rx.ts.lane.valid & ~rx.ts.link.valid & 
                    (((rx.ts.ts_id == 0) & ~rx.ts.ctrl.compliance_receive)
                    | ((rx.ts.ts_id == 0) & rx.ts.ctrl.loopback)
                    | (rx.ts.ts_id == 1))):

                        # Prevent overflows
                        with m.If(rx_ts_count < 8):
                            m.d.rx += rx_ts_count.eq(rx_ts_count + 1)
                        
                    # Otherwise if a TS is invalid, start counting again.
                    with m.Elif(rx_ts_count < 8):
                        m.d.rx += rx_ts_count.eq(0)

                # If 8 consecutive TSs fitting the conditions have been received, go to Polling.Configuration.
                with m.If((rx_ts_count >= 8) & (tx_ts_count >= 1024)):
                    reset_ts_count_and_jump(State.Polling_Configuration)
                
                # And if no 8 consecutive, valid TSs have been received for 24 ms, go to Detect.
                timeout(24, State.Detect)                               


            with m.State(State.Polling_Configuration):
                # Once arrived here go to Polling.Configuration.TS and send TS2 ordered sets with Link and Lane set to PAD
                # and reset the TS counters.
                m.d.rx += debug_state.eq(State.Polling_Configuration)
                reset_ts_count_and_jump(State.Polling_Configuration_TS)
                m.d.rx += [
                    tx.ts.valid.eq(1),
                    tx.ts.ts_id.eq(1),
                    tx.ts.link.valid.eq(0),
                    tx.ts.lane.valid.eq(0),
                    tx_ts_count.eq(0),
                ]
                m.d.rx += rx_ts_count.eq(0)


            with m.State(State.Polling_Configuration_TS):
                m.d.rx += debug_state.eq(State.Polling_Configuration_TS)

                with m.If(tx.start_send_ts):                            # When a TS is sent,
                    with m.If(rx_ts_count == 0):                        # as long as no TSs are received,
                        m.d.rx += tx_ts_count.eq(0)                     # reset the received TS count
                    with m.Else():
                        m.d.rx += tx_ts_count.eq(tx_ts_count + 1)       # Otherwise count sent TSs
                
                with m.If(rx.ts_received):
                    # Accept TS2s with Link and Lane set to PAD.
                    # After 8 consecutive ones have been received
                    # and after 16 TSs have been transmitter after receiving the first consecutive TS,
                    # go to Configuration.Linkwidth.Start
                    with m.If(rx.ts.valid & (rx.ts.ts_id == 1)
                    & ~rx.ts.link.valid & ~rx.ts.lane.valid):
                        with m.If(rx_ts_count < 8):
                            m.d.rx += rx_ts_count.eq(rx_ts_count + 1)
                    # and if an invalid one comes, reset the RX TS counter.
                    with m.Elif(rx_ts_count < 8):
                        m.d.rx += rx_ts_count.eq(0)             

                with m.If((tx_ts_count >= 16) & (rx_ts_count >= 8)):
                    reset_ts_count_and_jump(State.Configuration)
        
                # Otherwise go back to Detect after 48 milliseconds.
                timeout(48, State.Detect)


            with m.State(State.Configuration_Linkwidth_Start): # Is missing Loopback and Disabled
                m.d.rx += debug_state.eq(State.Configuration_Linkwidth_Start)
                # Send TS1 ordered sets with Link and Lane set to PAD
                m.d.rx += [
                    tx.ts.valid.eq(1),
                    tx.ts.ts_id.eq(0),
                    tx.ts.link.valid.eq(0),
                    tx.ts.lane.valid.eq(0),
                ]

                # Accept TS1s with Link=Upstream-Link Lane=PAD
                # and set the link number of the TSs being sent to the received link number
                # and go to Configuration.Linkwidth.Accept
                with m.If(rx.consecutive & rx.ts.valid & (rx.ts.ts_id == 0)
                & rx.ts.link.valid & ~rx.ts.lane.valid):
                    m.d.rx += tx.ts.link.valid.eq(1)
                    m.d.rx += tx.ts.link.number.eq(rx.ts.link.number)
                    reset_ts_count_and_jump(State.Configuration_Linkwidth_Accept)
                
                timeout(24, State.Detect)


            with m.State(State.Configuration_Linkwidth_Accept):
                m.d.rx += debug_state.eq(State.Configuration_Linkwidth_Accept)

                # Accept TS1 Link=Upstream-Link Lane=Upstream-Lane
                # with the lane number 0, in a x4 implementation it should be lane-dependent.
                # Report back that the received lane is valid.
                #with m.If(rx.ts_received):
                with m.If(rx.ts.valid & (rx.ts.ts_id == 0) & rx.ts.link.valid & rx.ts.lane.valid):
                    with m.If(rx.ts.lane.number == 0):
                        m.d.rx += tx.ts.lane.valid.eq(1)
                        m.d.rx += tx.ts.lane.number.eq(rx.ts.lane.number)
                        reset_ts_count_and_jump(State.Configuration_Lanenum_Wait)
                
                # After 2 milliseconds of invalid stuff being received or an invalid TS being received, go back.
                timeout(2, State.Detect, (rx.ts.valid & (rx.ts.ts_id == 0) & ~rx.ts.link.valid & ~rx.ts.lane.valid))


            with m.State(State.Configuration_Lanenum_Wait):
                m.d.rx += debug_state.eq(State.Configuration_Lanenum_Wait)


                # Accept TS1 Link=Upstream-Link Lane=Upstream-Lane
                # Two consecutive TS1 with lane number different than when this state was entered
                with m.If(rx.ts.valid & (rx.ts.ts_id == 0) & rx.ts.link.valid & rx.ts.lane.valid):
                    with m.If(rx.ts.lane.number != tx.ts.lane.number):
                        with m.If(rx.consecutive):
                            reset_ts_count_and_jump(State.Configuration_Lanenum_Accept)
                
                # Accept TS2
                with m.If(rx.ts.valid & (rx.ts.ts_id == 1) & rx.consecutive):
                    reset_ts_count_and_jump(State.Configuration_Lanenum_Accept)
                    
                # After 2 milliseconds of invalid stuff being received or an invalid TS being received, go back.
                timeout(2, State.Detect, (rx.ts.valid & (rx.ts.ts_id == 0) & ~rx.ts.link.valid & ~rx.ts.lane.valid))


            with m.State(State.Configuration_Lanenum_Accept): # Revise for multiple lanes
                m.d.rx += debug_state.eq(State.Configuration_Lanenum_Accept)

                # Accept consecutive TS2 Link=Upstream-Link Lane=Upstream-Lane
                with m.If(rx.ts.valid & (rx.ts.ts_id == 1) & rx.ts.link.valid & rx.ts.lane.valid):
                    with m.If((rx.ts.link.number == tx.ts.link.number) & (rx.ts.lane.number == tx.ts.lane.number)):
                        with m.If(rx.consecutive):
                            reset_ts_count_and_jump(State.Configuration_Complete)

                # But no two consecutive TS1s with invalid link and lane.
                with m.If(rx.ts.valid & (rx.ts.ts_id == 0) & ~rx.ts.link.valid & ~rx.ts.lane.valid):
                    with m.If(rx.consecutive):
                        reset_ts_count_and_jump(State.Detect)


            with m.State(State.Configuration_Complete):
                m.d.rx += debug_state.eq(State.Configuration_Complete)

                # Complete the configuration by sending TS1 packets with the configured values and request 255 fast training sequences for exiting L0s.
                # And reset the TS counts.
                m.d.rx += [
                    tx.ts.ts_id.eq(1),
                    tx.ts.n_fts.eq(0xFF),
                    tx_ts_count.eq(0)
                ]
                m.d.rx += rx_ts_count.eq(0)
                reset_ts_count_and_jump(State.Configuration_Complete_TS)


            with m.State(State.Configuration_Complete_TS):
                m.d.rx += debug_state.eq(State.Configuration_Complete_TS)

                # Start counting sent TSs after a TS has been received
                with m.If(tx.start_send_ts):
                    with m.If(rx_ts_count == 0):
                        m.d.rx += tx_ts_count.eq(0)
                    with m.Elif(tx_ts_count < 16):
                        m.d.rx += tx_ts_count.eq(tx_ts_count + 1)
                with m.If(rx.ts_received):
                    # Accept TS2 Link=Upstream-Link Lane=Upstream-Lane
                    # and wait for 8 consecutive ones, otherwise reset the counter
                    with m.If(rx.ts.valid & (rx.ts.ts_id == 1) & rx.ts.link.valid & rx.ts.lane.valid &
                        (rx.ts.link.number == tx.ts.link.number) &
                        (rx.ts.lane.number == tx.ts.lane.number) & rx.consecutive):
                        with m.Elif(rx_ts_count < 8):
                            m.d.rx += rx_ts_count.eq(rx_ts_count + 1)
                    with m.Else():
                        m.d.rx += rx_ts_count.eq(0)

                with m.If(rx_ts_count == 8):
                    with m.If(tx_ts_count == 16):
                        reset_ts_count_and_jump(State.Configuration_Idle)
                
                # After waiting for 2 milliseconds and no 8 valid consecutive TSs being received, go back to the beginning.
                timeout(2, State.Detect)


            with m.State(State.Configuration_Idle):
                m.d.rx += debug_state.eq(State.Configuration_Idle)

                # Send IDL symbols
                m.d.rx += tx.ts.valid.eq(0)
                m.d.rx += tx.idle.eq(1)
                m.d.rx += tx_ts_count.eq(0)
                m.d.rx += rx_ts_count.eq(0)

                # When 0x00 0x00 is received, wait until 8 have arrived and 16 sent after the first one has arrived.
                with m.If(lane.rx_symbol == 0):
                    with m.If(rx_idl_count < 4):
                        m.d.rx += rx_idl_count.eq(rx_idl_count + 1)
                        m.d.rx += tx_idl_count.eq(0)
                    with m.Else():
                        m.d.rx += tx_idl_count.eq(tx_idl_count + 1)
                        with m.If(tx_idl_count >= 8):
                            m.d.rx += tx.idle.eq(0)
                            m.d.rx += rx_idl_count.eq(0)
                            m.d.rx += tx_idl_count.eq(0)
                            reset_ts_count_and_jump(State.L0)
                with m.Else():
                    m.d.rx += rx_idl_count.eq(0)

                # And the link should be configured!
                #m.d.rx += status.link.up.eq(1)

                # Well, wait 2 milliseconds and if nothing happens, stop transmitting idle symbols and go to Recovery or Detect.
                timeout(2, State.Detect)
                #m.d.rx += timer.eq(timer + 1)
                #with m.If(timer == 2 * clocks_per_ms):
                #    m.d.rx += timer.eq(0)
                #    m.d.rx += tx.idle.eq(0)
                #    reset_ts_count_and_jump(State.Detect)
                    # This will need a revision for PCIe 2.0
                    #with m.If(status.idle_to_rlock_transitioned < 0xFF): # Set to 0xFF on transition to Recovery
                    #    reset_ts_count_and_jump(State.Recovery)
                    #with m.Else():
                    #    reset_ts_count_and_jump(State.Detect)

                        
            with m.State(State.Recovery_RcvrLock):
                m.d.rx += debug_state.eq(State.Recovery_RcvrLock)

                # Send TS1 ordered sets with same Link and Lane as configured
                m.d.rx += [
                    tx.ts.valid.eq(1),
                    tx.ts.ts_id.eq(0)
                ]

                # If a TS is received with the link and lane numbers matching the configured ones and 8 such have been received, go to Recovery.RcvrCfg
                with m.If(rx.ts_received & rx.ts.valid & rx.ts.link.valid & rx.ts.lane.valid &
                    (rx.ts.link.number == tx.ts.link.number) &
                    (rx.ts.lane.number == tx.ts.lane.number)):
                    m.d.rx += rx_ts_count.eq(rx_ts_count + 1)
                with m.If(rx_ts_count == 8):
                    reset_ts_count_and_jump(State.Recovery_RcvrCfg)

                # If no TSn but something else was received, reset the RX counter
                with m.If(~rx.recv_tsn): # Not consecutive, check if this works
                    m.d.rx += rx_ts_count.eq(0)
                
                timeout(24, State.Detect)


            with m.State(State.Recovery_RcvrCfg): # Revise when implementing 5 GT/s, page 290
                m.d.rx += debug_state.eq(State.Recovery_RcvrCfg)

                # Send TS2 ordered sets with same Link and Lane as configured
                m.d.rx += [
                    tx.ts.valid.eq(1),
                    tx.ts.ts_id.eq(1)
                ]

                last_ts = Signal()
                rx_recvd = Signal()

                # If two TSs dont have the same ID, reset the counter
                m.d.rx += last_ts.eq(rx.ts.ts_id)
                m.d.rx += rx_recvd.eq(rx_recvd | rx.ts_received)
                with m.If(tx.start_send_ts):
                    m.d.rx += tx_ts_count.eq(tx_ts_count + 1)
                with m.If(last_ts != rx.ts.ts_id):
                    m.d.rx += rx_ts_count.eq(0)
                
                # Count valid TS2s (valid link, lane, no speed change) and go to Recovery.Idle if so.
                with m.If(rx.ts_received & (rx.ts.ts_id == 1) & rx.ts.valid & rx.ts.link.valid & rx.ts.lane.valid & (rx.ts.rate.speed_change == 0) &
                    (rx.ts.link.number == tx.ts.link.number) &
                    (rx.ts.lane.number == tx.ts.lane.number)):
                    m.d.rx += rx_ts_count.eq(rx_ts_count + 1)
                with m.Else():
                    m.d.rx += rx_ts_count.eq(0)
                with m.If((rx_ts_count == 8) & (last_ts == 1)):
                    m.d.rx += last_ts.eq(0)
                    reset_ts_count_and_jump(State.Recovery_Idle)
                
                # If 8 TS1s have been received and 16 TS2s sent, go back to Configuration
                with m.If((rx_ts_count == 8) & (last_ts == 0) & (tx_ts_count == 16) & (rx.ts.rate.speed_change == 0)):
                    reset_ts_count_and_jump(State.Configuration)
                
                timeout(48, State.Detect)


            with m.State(State.Recovery_Idle):
                m.d.rx += debug_state.eq(State.Recovery_Idle)
                
                # Set the transmitter to send IDL symbols
                m.d.rx += tx.idle.eq(1)

                # If two invalid lanes has been received, go back to Configuration
                pad_cnt = Signal()
                with m.If(~rx.ts.lane.valid):
                    with m.If(~pad_cnt):
                        m.d.rx += pad_cnt.eq(1)
                    with m.Else():
                        reset_ts_count_and_jump(State.Configuration)
                
                # Wait for 8 IDL symbols, count 16 sent IDL symbols after first has been received, then go to L0 and reset idle_to_rlock_transitioned
                with m.If(lane.rx_symbol == Cat(Ctrl.IDL, Ctrl.IDL)):
                    with m.If(rx_idl_count < 4):
                        m.d.rx += rx_idl_count.eq(rx_idl_count + 1)
                        m.d.rx += tx_idl_count.eq(0)
                    with m.Else():
                        m.d.rx += tx_idl_count.eq(tx_idl_count + 1)
                        with m.If(tx_idl_count >= 8):
                            m.d.rx += status.idle_to_rlock_transitioned.eq(0)
                            m.d.rx += tx.idle.eq(0)
                            m.d.rx += rx_idl_count.eq(0)
                            m.d.rx += tx_idl_count.eq(0)
                            reset_ts_count_and_jump(State.L0)
                with m.Else():
                    m.d.rx += rx_idl_count.eq(0)
                
                # After 2 ms go back to the beginning of Recovery if idle_to_rlock_transitioned is less than 255, otherwise to Detect.
                timer = Signal(range(2 * clocks_per_ms + 1), reset = 2 * clocks_per_ms)
                m.d.rx += timer.eq(timer - 1)
                with m.If(timer == 0):
                    m.d.rx += tx.idle.eq(0)
                    with m.If(status.idle_to_rlock_transitioned < 0xFF):
                        reset_ts_count_and_jump(State.Recovery_RcvrLock)
                    with m.Else():
                        reset_ts_count_and_jump(State.Detect)


            with m.State(State.L0): # Page 297, implementation for 5 GT/s and higher lane counts missing
                m.d.rx += debug_state.eq(State.L0)
                # TBD
                m.d.rx += debug_state.eq(State.L0)
                m.d.rx += status.link.up.eq(1)
                with m.If(lane.rx_has_symbol(Ctrl.STP) | lane.rx_has_symbol(Ctrl.SDP)):
                    m.d.rx += status.idle_to_rlock_transitioned.eq(0)


        return m