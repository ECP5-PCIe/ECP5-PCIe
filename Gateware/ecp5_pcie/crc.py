from nmigen import *
from nmigen.build import *

class CRC(Elaboratable):

    """
    CRC generator for a variable number of data bits

    Parameters
    ----------
    input : Signal()
        Data input
    output : Signal()
        Data output
    init : int
        Initial CRC value
    polynomial : int
        CRC polynomial
    crc_size : int
        CRC size, for example 16 for CRC16.
    reset : Signal()
        Reset CRC Generator
    """
    def __init__(self, input, init, polynomial, crc_size, reset = Signal()):
        self.input      = input
        self.output     = Signal(crc_size, reset = init)
        self.init       = init
        self.reset      = reset
        self.polynomial = polynomial
        self.crc_size   = crc_size
    
    def elaborate(self, platform):
        m = Module()

        last = self.output
        for i in range(len(self.input)):
            in_val = self.input[i] ^ last[self.crc_size - 1]

            # All values to XOR
            in_vals = [None] * self.crc_size
            for j in range(self.crc_size):
                if (self.polynomial & (1 << j)) == 0:
                    in_vals[j] = 0
                else:
                    in_vals[j] = in_val

            current = Signal(self.crc_size)
            m.d.comb += current.eq((Cat(last) << 1)[0:self.crc_size] ^ Cat(in_vals))
            last = current
        
        with m.If(self.reset):
            m.d.sync += self.output.eq(self.init)
        with m.Else():
            m.d.sync += self.output.eq(last)

        return m
