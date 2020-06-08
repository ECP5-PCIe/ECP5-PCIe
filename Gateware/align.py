from nmigen import *
from nmigen.build import *
from nmigen.hdl.ast import Part


__all__ = ["SymbolSlip"]


class SymbolSlip(Elaboratable): # From Yumewatari
    """
    Symbol slip based comma aligner. Accepts and emits a sequence of words, shifting it such
    that if a comma symbol is encountered, it is always placed at the start of a word.

    If the input word contains multiple commas, the behavior is undefined.

    Parameters
    ----------
    symbol_size : int
        Symbol width, in bits.
    word_size : int
        Word size, in symbols.
    comma : int
        Comma symbol, ``symbol_size`` bit wide.

    Attributes
    ----------
    i : Signal(symbol_size * word_size)
        Input word.
    o : Signal(symbol_size * word_size)
        Output word.
    en : Signal
        Enable input. If asserted (the default), comma symbol affects alignment. Otherwise,
        comma symbol does nothing.
    """
    def __init__(self, symbol_size, word_size, comma):
        width = symbol_size * word_size

        self.i = Signal(width)
        self.o = Signal(width)
        self.en = Signal(reset=1)

        ###

        self.__width = width
        self.__word_size = word_size
        self.__symbol_size = symbol_size
        self.__comma = comma
    
    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        width = self.__width
        word_size = self.__word_size
        symbol_size = self.__symbol_size

        lastsamps = Signal(width * 2)
        m.d.rx += lastsamps.eq(Cat(lastsamps))
        m.d.rx += lastsamps.eq(Cat(lastsamps[width:], self.i))
        offset = Signal(range(word_size))
        m.d.rx += self.o.eq(lastsamps.bit_select(offset * symbol_size, width))
        for i in range(word_size):
            with m.If(lastsamps[i * symbol_size:(i + 1) * symbol_size] == self.__comma):
                m.d.rx += offset.eq(Mux(self.en, i, 0))
        return m