from nmigen import *
from nmigen.build import *
from serdes import K, D, Ctrl, PCIeSERDESInterface
from layouts import ts_layout

class PCIePhyRX(Elaboratable):
    """
    PCIe Receiver for 1:2 gearing

    Parameters
    ----------
    lane : PCIeSERDESInterface
        PCIe lane
    ts : Record(ts_layout)
        Data from received training sequence
    vlink : Signal
        Last valid link # received
    vlane : Signal
        Last valid lane # received
    """
    def __init__(self, lane):
        assert lane.ratio == 2
        self.lane = lane
        self.ts = Record(ts_layout)
        self.vlink = Signal(8)
        self.vlane = Signal(5)

    def elaborate(self, platform: Platform) -> Module: # TODO: Docstring
        m = Module()

        lane = self.lane
        ts = self.ts
        vlink = self.vlink
        vlane = self.vlane
        ts_last = Record(ts_layout)
        ts_current = Record(ts_layout)

        # The two received symbols
        symbol1 = lane.rx_symbol[0: 9]
        symbol2 = lane.rx_symbol[9:18]

        # Whether a TS is being received
        self.recv_tsn = recv_tsn = Signal()
        inverted = Signal()

        # Beginning to receive a TS
        self.start_receive_ts = Signal()

        # and receive it
        self.ts_received = Signal()


        # Structure of a TS:
        # COM Link Lane n_FTS Rate Ctrl ID ID ID ID ID ID ID ID ID ID
        # Link / Lane is invalid when PAD is being received.
        # In that case, the 9th bit is true.
        # Otherwise its valid and the link number gets stored.
        # There is also a SKP ordered set composed of COM SKP SKP SKP
        # A comma aligner before the RX causes the comma to be aligned to symbol1.
        with m.FSM(domain="rx"):
            with m.State("COMMA"):
                m.d.rx += self.ts_received.eq(0)

                with m.If(symbol1 == Ctrl.COM):
                    with m.If(symbol2 == Ctrl.PAD):
                        m.d.rx += ts_current.link.valid.eq(0)
                        m.next = "TSn-LANE-FTS"
                        m.d.rx += recv_tsn.eq(1)
                        
                    with m.If(symbol2 == Ctrl.SKP):
                        m.d.rx += recv_tsn.eq(0)
                        m.next = "SKP"

                    with m.If(symbol2[8] == 0):
                        m.d.rx += ts_current.link.number.eq(symbol2[:8])
                        m.d.rx += ts_current.link.valid.eq(1)
                        m.next = "TSn-LANE-FTS"
                        m.d.rx += recv_tsn.eq(1)
                     # Ignore the comma otherwise, could be a different ordered set
                with m.Else():
                    m.d.rx += recv_tsn.eq(0)

            # SKP ordered set, in COMMA there is 'COM SKP' and here is 'SKP SKP' in rx_symbol, after which it goes back to COMMA.
            with m.State("SKP"):
                m.next = "COMMA"

            # Lane and Fast Training Sequence count
            with m.State("TSn-LANE-FTS"):
                m.next = "TSn-DATA"
                m.d.rx += ts_current.valid.eq(1)
                m.d.rx += self.start_receive_ts.eq(1)
                with m.If(symbol2[8] == 0):
                    m.d.rx += ts_current.n_fts.eq(symbol2[:8])
                with m.If(symbol1 == Ctrl.PAD):
                    m.d.rx += ts_current.lane.valid.eq(0)
                with m.If(symbol1[8] == 0):
                    m.d.rx += ts_current.lane.valid.eq(1)
                    m.d.rx += ts_current.lane.number.eq(symbol1[:5])
            
            # Rate and Ctrl bytes
            with m.State("TSn-DATA"):
                m.next = "TSn-ID0"
                m.d.rx += self.start_receive_ts.eq(0)
                with m.If(symbol1[8] == 0):
                    m.d.rx += Cat(ts_current.rate).eq(symbol1[:8])
                with m.If(symbol2[8] == 0):
                    m.d.rx += Cat(ts_current.ctrl).eq(symbol2[:5])
                m.d.rx += ts_current.valid.eq(1)

            # Find out whether its a TS1, a TS2 or inverted
            for i in range(4):
                with m.State("TSn-ID%d" % i):
                    m.next = "TSn-ID%d" % (i + 1)
                    with m.If(symbol1 == D(10,2)):
                        m.d.rx += ts_current.ts_id.eq(0)
                        m.d.rx += inverted.eq(0)
                    with m.If(symbol1 == D(5,2)):
                        m.d.rx += ts_current.ts_id.eq(1)
                        m.d.rx += inverted.eq(0)
                    with m.If(symbol1 == D(21,5)):
                        m.d.rx += ts_current.ts_id.eq(0)
                        m.d.rx += inverted.eq(1)
                    with m.If(symbol1 == D(26,5)):
                        m.d.rx += ts_current.ts_id.eq(1)
                        m.d.rx += inverted.eq(1)

            # When its not inverted, accept it.
            # Additionally it can be checked whether two consecutive TSs are valid by uncommenting the if statement
            with m.State("TSn-ID4"):
                m.next = "COMMA"
                with m.If(inverted):
                    lane.rx_invert.eq(~lane.rx_invert) # Maybe it should change the disparity instead?
                    m.d.rx += ts.valid.eq(0)
                with m.Else():
                    #with m.If((ts_last == ts_current)):
                    m.d.rx += ts.eq(ts_current)
                    m.d.rx += ts_last.eq(ts_current)
                    m.d.rx += self.ts_received.eq(1)
        
        with m.If(ts.link.valid):
            m.d.rx += vlink.eq(ts.link.number)
        with m.If(ts.lane.valid):
            m.d.rx += vlane.eq(ts.lane.number)

        return m