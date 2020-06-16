from nmigen import *
from nmigen.build import *
from serdes import K, D, Ctrl, PCIeSERDESInterface
from layouts import ltssm_layout
from phy_tx import PCIePhyTX
from phy_rx import PCIePhyRX

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
        rx_ts_count = self.rx_ts_count
        tx_ts_count = self.tx_ts_count
        rx_idl_count = Signal(range(4 + 1))
        tx_idl_count = Signal(range(8 + 1))
        tx = self.tx
        rx = self.rx
        debug_state = self.debug_state

        m.d.comb += tx.ts.rate.gen1.eq(1)

        def timeout(time_in_ms, next_state, or_conds=0):
            timer = Signal(range(time_in_ms * clocks_per_ms + 1), reset=time_in_ms * clocks_per_ms)
            m.d.rx += timer.eq(timer - 1)
            with m.If((timer == 0) | or_conds):
                m.next = "Detect.Active"
            return timer


        with m.FSM(domain="rx"): # Page 249 onwards
            with m.State("Detect.Quiet"): # Change to 2.5 GT/s
                m.d.rx += debug_state.eq(0)
                m.d.rx += status.link.up.eq(0)
                m.d.tx += tx.eidle.eq(0b11)
                m.next = "Detect.Quiet.Timeout"

            with m.State("Detect.Quiet.Timeout"):
                m.d.rx += debug_state.eq(1)
                timeout(12, "Detect.Active", lane.rx_present)

            with m.State("Detect.Active"):
                m.d.tx += lane.det_enable.eq(1)
                m.d.rx += debug_state.eq(2)
                with m.If(lane.det_valid):
                    m.d.tx += lane.det_enable.eq(0)
                    with m.If(lane.det_status):
                        m.next = "Polling.Active"
                    with m.Else():
                        m.next = "Detect.Quiet"
            
            with m.State("Polling.Active"):
                m.d.rx += debug_state.eq(3)
                m.d.tx += [
                    tx.ts.valid.eq(1), # Send TS1 ordered sets with Link and Lane set to PAD
                    tx.ts.ts_id.eq(0),
                    tx.ts.link.valid.eq(0),
                    tx.ts.lane.valid.eq(0),
                    tx_ts_count.eq(0),
                ]
                m.d.rx += rx_ts_count.eq(0)
                m.next = "Polling.Active.TS"
            with m.State("Polling.Active.TS"):
                m.d.rx += debug_state.eq(4)
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
                                m.next = "Polling.Configuration"
                        with m.Else():
                            m.d.rx += rx_ts_count.eq(0)
                timeout(24, "Detect.Quiet")
            with m.State("Polling.Configuration"):
                m.d.rx += debug_state.eq(5)
                m.next = "Polling.Configuration.TS"
                m.d.tx += [
                    tx.ts.valid.eq(1), # Send TS2 ordered sets with Link and Lane set to PAD
                    tx.ts.ts_id.eq(1),
                    tx.ts.link.valid.eq(0),
                    tx.ts.lane.valid.eq(0),
                    tx_ts_count.eq(0),
                ]
                m.d.rx += rx_ts_count.eq(0)
            with m.State("Polling.Configuration.TS"):
                m.d.rx += debug_state.eq(6)
                timeout(48, "Detect.Quiet")
                with m.If(tx.start_send_ts):
                    with m.If(rx_ts_count == 0):
                        m.d.tx += tx_ts_count.eq(0)
                    with m.Else():
                        m.d.tx += tx_ts_count.eq(tx_ts_count + 1)
                with m.If(rx.ts_received):
                    with m.If(rx.ts.valid & (rx.ts.ts_id == 1) & ~rx.ts.link.valid & ~rx.ts.lane.valid): # Accept TS2 Link=PAD Lane=PAD
                        with m.If(rx_ts_count == 8):
                            with m.If(tx_ts_count >= 16):
                                m.next = "Configuration.Linkwidth.Start"
                        with m.Else():
                            m.d.rx += rx_ts_count.eq(rx_ts_count + 1)
                    with m.Else():
                        m.d.rx += rx_ts_count.eq(0)
            with m.State("Configuration.Linkwidth.Start"):
                m.d.rx += debug_state.eq(7)
                m.d.tx += [
                    tx.ts.valid.eq(1), # Send TS1 ordered sets with Link and Lane set to PAD
                    tx.ts.ts_id.eq(0),
                    tx.ts.link.valid.eq(0),
                    tx.ts.lane.valid.eq(0),
                ]
                with m.If(rx.ts.valid & (rx.ts.ts_id == 0) & rx.ts.link.valid & ~rx.ts.lane.valid): # Accept TS1 Link=Upstream-Link Lane=PAD
                    m.d.tx += tx.ts.link.valid.eq(1)
                    m.d.tx += tx.ts.link.number.eq(rx.ts.link.number)
                    m.next = "Configuration.Linkwidth.Accept"
                timeout(24, "Detect.Quiet")
            with m.State("Configuration.Linkwidth.Accept"):
                m.d.rx += debug_state.eq(8)
                # Accept TS1 Link=Upstream-Link Lane=Upstream-Lane
                with m.If(rx.ts.valid & (rx.ts.ts_id == 0) & rx.ts.link.valid & rx.ts.lane.valid):
                    with m.If(rx.ts.lane.number == 0): # Accept lane number 0, in a x4 implementation it should depend on the lane
                        m.d.tx += tx.ts.lane.valid.eq(1)
                        m.d.tx += tx.ts.lane.number.eq(rx.ts.lane.number)
                        m.next = "Configuration.Lanenum.Wait"
                # Accept TS1 Link=PAD Lane=PAD
                timeout(2, "Detect.Quiet", (rx.ts.valid & (rx.ts.ts_id == 0) & ~rx.ts.link.valid & ~rx.ts.lane.valid))
            with m.State("Configuration.Lanenum.Wait"):
                m.d.rx += debug_state.eq(9)
                # Accept TS1 Link=Upstream-Link Lane=Upstream-Lane
                with m.If(rx.ts.valid & (rx.ts.ts_id == 0) & rx.ts.link.valid & rx.ts.lane.valid):
                    with m.If(rx.ts.lane.number != tx.ts.lane.number):
                        m.next = "Configuration.Lanenum.Accept"
                # Accept TS2
                with m.If(rx.ts.valid & (rx.ts.ts_id == 1)):
                    m.next = "Configuration.Lanenum.Accept"
                # Accept TS1 Link=PAD Lane=PAD
                timeout(2, "Detect.Quiet", (rx.ts.valid & (rx.ts.ts_id == 0) & ~rx.ts.link.valid & ~rx.ts.lane.valid))
            with m.State("Configuration.Lanenum.Accept"):
                m.d.rx += debug_state.eq(10)
                # Accept TS2 Link=Upstream-Link Lane=Upstream-Lane
                with m.If(rx.ts.valid & (rx.ts.ts_id == 1) & rx.ts.link.valid & rx.ts.lane.valid):
                    with m.If((rx.ts.link.number == tx.ts.link.number) & (rx.ts.lane.number == tx.ts.lane.number)):
                        m.next = "Configuration.Complete"
                    with m.Else():
                        m.next = "Detect.Quiet"
                with m.If(rx.ts.valid & (rx.ts.ts_id == 0) & ~rx.ts.link.valid & ~rx.ts.lane.valid):
                    m.next = "Detect.Quiet"
            with m.State("Configuration.Complete"):
                m.d.rx += debug_state.eq(11)
                m.d.tx += [
                    tx.ts.ts_id.eq(1),
                    tx.ts.n_fts.eq(0xFF),
                    tx_ts_count.eq(0)
                ]
                m.d.rx += rx_ts_count.eq(0)
                m.next = "Configuration.Complete.TS"
            with m.State("Configuration.Complete.TS"):
                m.d.rx += debug_state.eq(12)
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
                                m.next = "Configuration.Idle"
                        with m.Else():
                            m.d.rx += rx_ts_count.eq(rx_ts_count + 1)
                    with m.Else():
                        m.d.rx += rx_ts_count.eq(0)
                timeout(2, "Detect.Quiet")
            with m.State("Configuration.Idle"):
                m.d.tx += tx.ts.valid.eq(0)
                m.d.tx += tx.idle.eq(1)
                m.d.tx += tx_ts_count.eq(0)
                m.d.rx += rx_ts_count.eq(0)
                m.d.rx += debug_state.eq(13)
                with m.If(lane.rx_symbol == Cat(Ctrl.IDL, Ctrl.IDL)):
                    with m.If(rx_idl_count < 4):
                        m.d.rx += rx_idl_count.eq(rx_idl_count + 1)
                        m.d.tx += tx_idl_count.eq(0)
                    with m.Else():
                        m.d.tx += tx_idl_count.eq(tx_idl_count + 1)
                        with m.If(tx_idl_count >= 8):
                            m.d.tx += tx.idle.eq(0)
                            m.next = "L0"
                with m.Else():
                    m.d.rx += rx_idl_count.eq(0)
                #m.d.tx += lane.tx_symbol.eq(Cat(Ctrl.IDL, Ctrl.IDL))
                m.d.rx += status.link.up.eq(1)
                timer = Signal(range(2 * clocks_per_ms + 1), reset = 2 * clocks_per_ms)
                m.d.rx += timer.eq(timer - 1)
                with m.If(timer == 0):
                    m.d.tx += tx.idle.eq(0)
                    with m.If(status.idle_to_rlock_transitioned < 0xFF): # Set to 0xFF on transition to Recovery.RcvrLock
                        m.next = "Recovery.RcvrLock"
                    with m.Else():
                        m.next = "Detect.Quiet"
            with m.State("Recovery.RcvrLock"):
                m.d.rx += debug_state.eq(14)
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
                    m.next = "Recovery.RcvrCfg"
                with m.If(~rx.recv_tsn): # Not consecutive, check if this works
                    m.d.rx += rx_ts_count.eq(0)
                timeout(24, "Detect.Quiet")
            with m.State("Recovery.RcvrCfg"): # Revise when implementing 5 GT/s, page 290
                m.d.rx += debug_state.eq(15)
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
                    m.next = "Recovery.Idle"
                with m.If((rx_ts_count == 8) & (last_ts == 0) & (tx_ts_count == 16) & (rx.ts.rate.speed_change == 0)):
                    m.next = "Configuration.Linkwidth.Start"
                timeout(48, "Detect.Quiet")
            with m.State("Recovery.Idle"):
                m.d.rx += debug_state.eq(16)
                pad_cnt = Signal(1)
                with m.If(~rx.ts.lane.valid):
                    with m.If(~pad_cnt):
                        m.d.rx += pad_cnt.eq(1)
                    with m.Else():
                        m.next = "Configuration.Linkwidth.Start"
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
                            m.next = "L0"
                with m.Else():
                    m.d.rx += rx_idl_count.eq(0)
                timer = Signal(range(2 * clocks_per_ms + 1), reset = 2 * clocks_per_ms)
                m.d.rx += timer.eq(timer - 1)
                with m.If(timer == 0):
                    m.d.tx += tx.idle.eq(0)
                    with m.If(status.idle_to_rlock_transitioned < 0xFF):
                        m.next = "Recovery.RcvrLock"
                    with m.Else():
                        m.next = "Detect.Quiet"
            with m.State("L0"): # Page 297, implementation for 5 GT/s and higher lane counts missing
                m.d.rx += debug_state.eq(255)
                m.d.rx += status.link.up.eq(1)
                with m.If(lane.rx_has_symbol(Ctrl.STP) | lane.rx_has_symbol(Ctrl.SDP)):
                    m.d.rx += status.idle_to_rlock_transitioned.eq(0)
        return m