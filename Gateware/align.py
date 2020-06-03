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

        self.__shreg  = Signal(width * 2)
        self.__offset = Signal(range(symbol_size * (word_size - 1))) # Maybe add +1?
        self.__width = width
        self.__word_size = word_size
        self.__symbol_size = symbol_size
        self.__comma = comma
    
    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        m.d.sync += self.__shreg.eq(Cat(self.__shreg[self.__width:], self.i))
        m.d.comb += self.o.eq(Part(self.__shreg, self.__offset, self.__width))

        commas = Signal(self.__word_size)
        m.d.sync += [
            commas[n].eq(Part(self.i, self.__symbol_size * n, self.__symbol_size) == self.__comma)
            for n in range(self.__word_size)
        ]

        with m.If(self.en):
            with m.Switch(commas):
                for n in range(self.__word_size):
                    with m.Case(1 << n):
                        self.__offset.eq(self.__symbol_size * n)
        
        return m