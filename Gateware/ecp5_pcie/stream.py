from nmigen import *

class StreamInterface(Elaboratable): # From Yumewatari
    """
    Interface of a single PCIe SERDES pair, connected to a single lane. Uses 1:**ratio** gearing
    for configurable **ratio**, i.e. **ratio** symbols are transmitted per clock cycle.

    Parameters
    ----------
    symbol_size : int
        Size of one symbol in bits.
    word_size : int
        Number fo symbols per clock cycle.

    symbol : [Signal(symbol_size)] * word_size
        The symbol(s) being transferred when valid = 1 and ready = 1
    valid : [Signal()] * word_size
        Asserted if the symbol is valid and should be processed.
    ready : Signal()
        Asserted when the receiver is ready´
    """
    def __init__(self, symbol_size, word_size):
        self.symbol       = [Signal(symbol_size)] * word_size
        self.valid        = [Signal()] * word_size
        self.ready        = Signal()