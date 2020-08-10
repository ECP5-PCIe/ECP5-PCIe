from nmigen import *
from nmigen.build import *
from nmigen.hdl.ast import Part
from nmigen.lib.fifo import AsyncFIFOBuffered
from nmigen.lib.cdc import FFSynchronizer

from enum import IntEnum

from .align import SymbolSlip


__all__ = ["PCIeSERDESInterface", "PCIeSERDESAligner"]


def K(x, y): return (1 << 8) | (y << 5) | x
def D(x, y): return (0 << 8) | (y << 5) | x

class Ctrl(IntEnum):
    PAD = K(23, 7)
    STP = K(27, 7) # Start Transaction Layer Packet
    SKP = K(28, 0) # Skip
    FTS = K(28, 1) # Fast Training Sequence
    SDP = K(28, 2) # Start Data Link Layer Packet
    IDL = K(28, 3) # Idle
    COM = K(28, 5) # Comma
    EIE = K(28, 7) # Electrical Idle Exit
    END = K(29, 7)
    EDB = K(30, 7) # End Bad
    



class PCIeSERDESInterface(Elaboratable): # From Yumewatari
    """
    Interface of a single PCIe SERDES pair, connected to a single lane. Uses 1:**ratio** gearing
    for configurable **ratio**, i.e. **ratio** symbols are transmitted per clock cycle.

    Parameters
    ----------
    ratio : int
        Gearbox ratio.

    rx_invert : Signal
        Assert to invert the received bits before 8b10b decoder.
    rx_align : Signal
        Assert to enable comma alignment state machine, deassert to lock alignment.
    rx_present : Signal
        Asserted if the receiver has detected signal.
    rx_locked : Signal
        Asserted if the receiver has recovered a valid clock.
    rx_aligned : Signal
        Asserted if the receiver has aligned to the comma symbol.

    rx_symbol : Signal(9 * ratio)
        Two 8b10b-decoded received symbols, with 9th bit indicating a control symbol.
    rx_valid : Signal(ratio)
        Asserted if the received symbol has no coding errors. If not asserted, ``rx_data`` and
        ``rx_control`` must be ignored, and may contain symbols that do not exist in 8b10b coding
        space.

    tx_locked : Signal
        Asserted if the transmitter is generating a valid clock.

    tx_symbol : Signal(9 * ratio)
        Symbol to 8b10b-encode and transmit, with 9th bit indicating a control symbol.
    tx_set_disp : Signal(ratio)
        Assert to indicate that the 8b10b encoder should choose an encoding with a specific
        running disparity instead of using its state, specified by ``tx_disp``.
    tx_disp : Signal(ratio)
        Assert to transmit a symbol with positive running disparity, deassert for negative
        running disparity.
    tx_e_idle : Signal(ratio)
        Assert to transmit Electrical Idle for that symbol.

    det_enable : Signal
        Rising edge starts the Receiver Detection test. Transmitter must be in Electrical Idle
        when ``det_enable`` is asserted.
    det_valid : Signal
        Asserted to indicate that the Receiver Detection test has finished, deasserted together
        with ``det_enable``.
    det_status : Signal
        Valid when ``det_valid`` is asserted. Indicates whether a receiver has been detected
        on this lane.
    """
    def __init__(self, ratio=1):
        self.ratio        = ratio

        self.rx_invert    = Signal()
        self.rx_align     = Signal()
        self.rx_present   = Signal()
        self.rx_locked    = Signal()
        self.rx_aligned   = Signal()

        self.rx_symbol    = Signal(ratio * 9)
        self.rx_valid     = Signal(ratio)

        self.tx_symbol    = Signal(ratio * 9)
        self.tx_set_disp  = Signal(ratio)
        self.tx_disp      = Signal(ratio)
        self.tx_e_idle    = Signal(ratio)
        self.tx_locked    = Signal()

        self.det_enable   = Signal()
        self.det_valid    = Signal()
        self.det_status   = Signal()
    
    def rx_has_symbol(self, symbol):
        has = False
        for i in range(self.ratio):
            has |= self.rx_symbol[i * 9 : i * 9 + 9] == symbol
        return has

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        return m


class PCIeSERDESAligner(PCIeSERDESInterface):
    """
    A multiplexer that aligns commas to the first symbol of the word, for SERDESes that only
    perform bit alignment and not symbol alignment.
    """
    def __init__(self, lane):
        self.ratio        = lane.ratio

        self.rx_invert    = lane.rx_invert
        self.rx_align     = lane.rx_align
        self.rx_present   = lane.rx_present
        self.rx_locked    = lane.rx_locked
        self.rx_aligned   = lane.rx_aligned

        self.rx_symbol    = Signal(lane.ratio * 9)
        self.rx_valid     = Signal(lane.ratio)

        self.tx_symbol    = Signal(lane.ratio * 9)
        self.tx_set_disp  = Signal(lane.ratio)
        self.tx_disp      = Signal(lane.ratio)
        self.tx_e_idle    = Signal(lane.ratio)

        self.det_enable   = lane.det_enable
        self.det_valid    = lane.det_valid
        self.det_status   = lane.det_status

        self.__lane = lane

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        # Do TX CDC
        # FFSynchronizer
        if False:
            m.submodules += FFSynchronizer(Cat(self.tx_symbol, self.tx_set_disp, self.tx_disp, self.tx_e_idle), Cat(self.__lane.tx_symbol, self.__lane.tx_set_disp, self.__lane.tx_disp, self.__lane.tx_e_idle), o_domain="tx", stages=4)
        
        # No CDC
        if False:
            m.d.comb += Cat(self.__lane.tx_symbol, self.__lane.tx_set_disp, self.__lane.tx_disp, self.__lane.tx_e_idle).eq(
                Cat(self.tx_symbol, self.tx_set_disp, self.tx_disp, self.tx_e_idle))

        # AsyncFIFOBuffered
        if True:
            tx_fifo = m.submodules.tx_fifo = AsyncFIFOBuffered(width=24, depth=10, r_domain="tx", w_domain="rx")
            m.d.comb += tx_fifo.w_data.eq(Cat(self.tx_symbol, self.tx_set_disp, self.tx_disp, self.tx_e_idle))
            m.d.comb += Cat(self.__lane.tx_symbol, self.__lane.tx_set_disp, self.__lane.tx_disp, self.__lane.tx_e_idle).eq(tx_fifo.r_data)
            m.d.comb += tx_fifo.r_en.eq(1)
            m.d.comb += tx_fifo.w_en.eq(1)

        # Testing symbols
        if False:
            m.d.comb += self.__lane.tx_symbol.eq(Cat(Ctrl.COM, D(10, 2)))


        self.slip = SymbolSlip(symbol_size=10, word_size=self.__lane.ratio, comma=Cat(Ctrl.COM, 1))
        m.submodules += self.slip
        
        m.d.comb += [
            self.slip.en.eq(self.rx_align),
            self.slip.i.eq(Cat(
                (self.__lane.rx_symbol.word_select(n, 9), self.__lane.rx_valid[n])
                for n in range(self.__lane.ratio)
            )),
            self.rx_symbol.eq(Cat(
                Part(self.slip.o, 10 * n, 9)
                for n in range(self.__lane.ratio)
            )),
            self.rx_valid.eq(Cat(
                self.slip.o[10 * n + 9]
                for n in range(self.__lane.ratio)
            )),
        ]
        return m