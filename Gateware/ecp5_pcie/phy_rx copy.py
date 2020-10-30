from nmigen import *
from nmigen.build import *
from nmigen.lib.fifo import SyncFIFOBuffered
from .serdes import K, D, Ctrl, PCIeSERDESInterface, PCIeScrambler
from .layouts import ts_layout

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
    fifo_depth : int
        How deep the FIFO to store received data is
    ready : Signal()
        Asserted by LTSSM to enable data reception
    fifo : SyncFIFOBuffered()
        Received data gets stored in here
    """
    def __init__(self, raw_lane : PCIeSERDESInterface, decoded_lane : PCIeScrambler, fifo_depth = 256):
        assert raw_lane.ratio == 2
        self.raw_lane = raw_lane
        self.decoded_lane = decoded_lane
        self.ts = Record(ts_layout)
        self.vlink = Signal(8)
        self.vlane = Signal(5)
        self.consecutive = Signal()
        self.inverted = Signal()
        self.ready = Signal()
        self.fifo = DomainRenamer("rx")(SyncFIFOBuffered(width=18, depth=fifo_depth))
    
    """
    Whether the symbol is in the current RX data
    """
    def has_symbol(self, symbol):
        has = False
        for i in range(self.decoded_lane.ratio):
            has |= self.decoded_lane.rx_symbol[i * 9 : i * 9 + 9] == symbol
        return has

    def elaborate(self, platform: Platform) -> Module: # TODO: Docstring
        m = Module()

        raw_lane = self.raw_lane
        decoded_lane = self.decoded_lane
        ts = self.ts
        vlink = self.vlink
        vlane = self.vlane
        ts_last = Record(ts_layout)
        ts_current = Record(ts_layout)

        self.idle = decoded_lane.rx_symbol == 0

        # The two received symbols
        symbol1 = raw_lane.rx_symbol[0: 9]
        symbol2 = raw_lane.rx_symbol[9:18]
        decoded_symbol1 = decoded_lane.rx_symbol[0: 9]
        decoded_symbol2 = raw_lane.rx_symbol[9:18]

        # Store received data
        m.submodules.fifo = fifo = self.fifo
        m.d.rx += fifo.w_en.eq(0)

        # Whether a TS is being received
        self.recv_tsn = recv_tsn = Signal()

        # Beginning to receive a TS
        self.start_receive_ts = Signal()

        # and receive it
        self.ts_received = Signal()

        # Whether the TS is inverted
        inverted = self.inverted # Signal()

        # Whether currently a DLLP or TLP is being received
        receiving_data = Signal()

        # Limit inversion rate, because inverting takes a while to propagate.
        # Otherwise it will oscillate and return garbage.
        # (And the moment when the inversion happens, the symbol will be garbled, since it isn't aligned to symbol boundaries.)
        last_invert = Signal(8)
        with m.If(last_invert != 0):
            m.d.rx += last_invert.eq(last_invert - 1)


        # Structure of a TS:
        # COM Link Lane n_FTS Rate Ctrl ID ID ID ID ID ID ID ID ID ID
        # Link / Lane is invalid when PAD is being received.
        # In that case, the 9th bit is true.
        # Otherwise its valid and the link number gets stored.
        # There is also a SKP ordered set composed of COM SKP SKP SKP
        # A comma aligner before the RX causes the comma to be aligned to symbol1.
        with m.FSM(domain="rx"):
            with m.State("IDLE"):
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
                with m.Elif(self.ready): # Might overflow
                    with m.If((decoded_symbol1 == Ctrl.SDP) | (decoded_symbol1 == Ctrl.STP) | receiving_data):
                        with m.If((decoded_symbol1 == Ctrl.COM) | (decoded_symbol2 == Ctrl.SKP)):
                            m.d.rx += fifo.w_en.eq(0)
                        with m.Else():
                            m.d.rx += [
                                receiving_data.eq(1),
                                fifo.w_data.eq(Cat(decoded_symbol1, decoded_symbol2)),
                                fifo.w_en.eq(1),
                            ]
                    with m.If((decoded_symbol2 == Ctrl.END) | (decoded_symbol2 == Ctrl.EDB)):
                        m.d.rx += receiving_data.eq(0)

                #9with m.Else():
                #    m.d.rx += recv_tsn.eq(0)

            # SKP ordered set, in COMMA there is 'COM SKP' and here is 'SKP SKP' in rx_symbol, after which it goes back to COMMA.
            with m.State("SKP"):
                m.next = "IDLE"

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
                    with m.If(symbol1 == D(5,2)):
                        m.d.rx += ts_current.ts_id.eq(1)
                    with m.If(symbol1 == D(21,5)):
                        m.d.rx += ts_current.ts_id.eq(0)
                        m.d.rx += inverted.eq(1)
                    with m.If(symbol1 == D(26,5)):
                        m.d.rx += ts_current.ts_id.eq(1)
                        m.d.rx += inverted.eq(1)

            # When its not inverted, accept it.
            # Additionally it can be checked whether two consecutive TSs are valid by uncommenting the if statement
            with m.State("TSn-ID4"):
                m.next = "IDLE"
                with m.If(inverted):
                    m.d.rx += ts.valid.eq(0)
                    m.d.rx += inverted.eq(0)
                    with m.If(last_invert == 0):
                        m.d.rx += raw_lane.rx_invert.eq(~raw_lane.rx_invert) # Maybe it should change the disparity instead?
                        m.d.rx += last_invert.eq(200)
                
                # If its not inverted, then a valid TS was received.
                with m.Else():
                    #with m.If((ts_last == ts_current)):
                    m.d.rx += ts.eq(ts_current)
                    m.d.rx += ts_last.eq(ts_current)
                    m.d.rx += self.ts_received.eq(1)

                    # Consecutive TS sensing
                    m.d.rx += self.consecutive.eq(ts_last == ts_current)
        
        with m.If(ts.link.valid):
            m.d.rx += vlink.eq(ts.link.number)
        with m.If(ts.lane.valid):
            m.d.rx += vlane.eq(ts.lane.number)

        return m