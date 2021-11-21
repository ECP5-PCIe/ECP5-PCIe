from nmigen import *
from .serdes import ctrl_set, Ctrl

class StreamInterface(): # From Yumewatari
    """
    A generic stream for connecting different modules together

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
    def __init__(self, symbol_size, word_size, name="", decode_9b_symbols=True):
        def stream_decoder(value : int):
            if value in ctrl_set:
                return Ctrl(value).name
            else:
                return hex(value)[2:]

        if symbol_size == 9 and decode_9b_symbols:
            self.symbol = [Signal(symbol_size, name=f"{name}_{i + 1}", decoder=stream_decoder) for i in range(word_size)]
        else:
            self.symbol = [Signal(symbol_size, name=f"{name}_{i + 1}") for i in range(word_size)]
        self.valid  = [Signal(name=f"{name}_{i + 1}V")             for i in range(word_size)]
        
        #self.debug  = Signal((symbol_size + 1) * word_size, name=name), decoder=stream_decoder)

        sigs = self.valid[0]
        for i in range(1, word_size):
            sigs |= self.valid[i]

        self.all_valid = sigs
        self.ready  =  Signal()
    
    """
    Connects a source to a sink.
    Returns nMigen statements which need to be added to a domain. For example 'm.d.comb += source.connect(sink)'

    Parameters
    ----------
    sink : StreamInterface
        The sink to connect this source to
    domain : nMigen domain to add statements to
        For example m.d.comb
    """
    def connect(self, sink, domain):
        assert len(self.symbol) == len(sink.symbol)

        for i in range(len(self.symbol)):
            domain += sink.symbol[i].eq(self.symbol[i])
            domain += sink.valid[i].eq(self.valid[i])

        domain += self.ready.eq(sink.ready)

        #domain += self.debug.eq(Cat(self.symbol, self.valid)) TODO: This doesn't show up in GTKWave
