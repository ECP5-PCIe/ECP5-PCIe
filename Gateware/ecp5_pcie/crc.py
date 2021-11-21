from nmigen import *
from nmigen.build import *

class SingleCRC(Elaboratable):

    """
    CRC generator for a variable number of data bits, calculates CRC of inputted data bits combinatorially

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
    def __init__(self, input, init, polynomial, crc_size):
        self.input      = input
        self.output     = Signal(crc_size, reset = init)
        self.init       = init
        self.polynomial = polynomial
        self.crc_size   = crc_size
    
    def elaborate(self, platform):
        m = Module()

        last = Const(self.init)
        for i in range(len(self.input)):
            # The input value is the input data XORed with the last bit of the CRC
            in_val = self.input[i] ^ last[self.crc_size - 1]

            # All values to XOR
            in_vals = [None] * self.crc_size
            for j in range(self.crc_size):
                # If the polynomial is 1 at a bit, XOR it with that bit in the input value
                if (self.polynomial & (1 << j)) == 0:
                    in_vals[j] = 0
                else:
                    in_vals[j] = in_val

            # Current CRC value
            current = Signal(self.crc_size) # This needs to be a signal, otherwise the simulation doesn't work
            # Shift the last CRC value and XOR all bits of it which are 1 in the polynomial with the input value
            m.d.comb += current.eq((Cat(last) << 1)[0:self.crc_size] ^ Cat(in_vals))
            last = current
    
        m.d.comb += self.output.eq(last)

        return m

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
    def __init__(self, input, init, polynomial, crc_size, reset):
        self.input      = input
        self.output     = Signal(crc_size, reset = init)
        self.init       = init
        self.polynomial = polynomial
        self.crc_size   = crc_size
        self.reset      = reset
    
    def elaborate(self, platform): # TODO: Apparently this generates 512 wires
        m = Module()

        last = self.output
        for i in range(len(self.input)):
            # The input value is the input data XORed with the last bit of the CRC
            in_val = self.input[i] ^ last[self.crc_size - 1]

            # All values to XOR
            in_vals = [None] * self.crc_size
            for j in range(self.crc_size):
                # If the polynomial is 1 at a bit, XOR it with that bit in the input value
                if (self.polynomial & (1 << j)) == 0:
                    in_vals[j] = 0
                else:
                    in_vals[j] = in_val

            # Current CRC value
            current = Signal(self.crc_size) # This needs to be a signal, otherwise the simulation doesn't work
            # Shift the last CRC value and XOR all bits of it which are 1 in the polynomial with the input value
            m.d.comb += current.eq((Cat(last) << 1)[0:self.crc_size] ^ Cat(in_vals))
            last = current
        
        # Setting the output to the initial value resets it
        with m.If(self.reset):
            m.d.sync += self.output.eq(self.init)
        with m.Else():
            m.d.sync += self.output.eq(last)

        return m

class LCRC(Elaboratable):

    """
    LCRC generator for a variable number of data bits

    Parameters
    ----------
    input : Signal()
        Data input
    output : Signal()
        Data output
    crc_size : int
        CRC size, for example 16 for CRC16.
    reset : Signal()
        Reset CRC Generator
    """
    def __init__(self, input, reset):
        self.input      = input
        self.init       = 0xFFFFFFFF
        self.polynomial = 0x04C11DB7
        self.crc_size   = 32
        self.reset      = reset
        self.output     = Signal(self.crc_size, reset = self.init)
    
    def elaborate(self, platform): # TODO: Apparently this generates 512 wires
        m = Module()

        last_reset = Signal()
        m.d.sync += last_reset.eq(self.reset)

        self.intermediate = Signal(self.crc_size, reset = self.init)

        if len(self.input) == 32:
            with m.If(last_reset & ~self.reset):
                last = self.intermediate
                for i in range(16):
                    # The input value is the input data XORed with the last bit of the CRC
                    in_val = self.input[i] ^ last[self.crc_size - 1]

                    # All values to XOR
                    in_vals = [None] * self.crc_size
                    for j in range(self.crc_size):
                        # If the polynomial is 1 at a bit, XOR it with that bit in the input value
                        if (self.polynomial & (1 << j)) == 0:
                            in_vals[j] = 0
                        else:
                            in_vals[j] = in_val

                    # Current CRC value
                    current = Signal(self.crc_size) # This needs to be a signal, otherwise the simulation doesn't work
                    # Shift the last CRC value and XOR all bits of it which are 1 in the polynomial with the input value
                    #m.d.comb += current[:16].eq(0xFFFF)
                    #m.d.comb += current[16:].eq((Cat(last) << 1)[0 : self.crc_size] ^ Cat(in_vals))
                    m.d.comb += current.eq((Cat(last) << 1)[0 : self.crc_size] ^ Cat(in_vals))
                    last = current

                # Setting the output to the initial value resets it
                with m.If(self.reset):
                    m.d.sync += self.intermediate.eq(self.init)
                with m.Else():
                    m.d.sync += self.intermediate.eq(last)
            
            with m.Else():
                last = self.intermediate
                for i in range(len(self.input)):
                    # The input value is the input data XORed with the last bit of the CRC
                    in_val = self.input[i] ^ last[self.crc_size - 1]

                    # All values to XOR
                    in_vals = [None] * self.crc_size
                    for j in range(self.crc_size):
                        # If the polynomial is 1 at a bit, XOR it with that bit in the input value
                        if (self.polynomial & (1 << j)) == 0:
                            in_vals[j] = 0
                        else:
                            in_vals[j] = in_val

                    # Current CRC value
                    current = Signal(self.crc_size) # This needs to be a signal, otherwise the simulation doesn't work
                    # Shift the last CRC value and XOR all bits of it which are 1 in the polynomial with the input value
                    m.d.comb += current.eq((Cat(last) << 1)[0 : self.crc_size] ^ Cat(in_vals))
                    last = current

                # Setting the output to the initial value resets it
                with m.If(self.reset):
                    m.d.sync += self.intermediate.eq(self.init)
                with m.Else():
                    m.d.sync += self.intermediate.eq(last)
        
        else:
            last = self.intermediate
            for i in range(len(self.input)):
                # The input value is the input data XORed with the last bit of the CRC
                in_val = self.input[i] ^ last[self.crc_size - 1]

                # All values to XOR
                in_vals = [None] * self.crc_size
                for j in range(self.crc_size):
                    # If the polynomial is 1 at a bit, XOR it with that bit in the input value
                    if (self.polynomial & (1 << j)) == 0:
                        in_vals[j] = 0
                    else:
                        in_vals[j] = in_val

                # Current CRC value
                current = Signal(self.crc_size) # This needs to be a signal, otherwise the simulation doesn't work
                # Shift the last CRC value and XOR all bits of it which are 1 in the polynomial with the input value
                m.d.comb += current.eq((Cat(last) << 1)[0 : self.crc_size] ^ Cat(in_vals))
                last = current
            
            # Setting the output to the initial value resets it
            with m.If(self.reset):
                m.d.sync += self.intermediate.eq(self.init)
            with m.Else():
                m.d.sync += self.intermediate.eq(last)
        
        for i in [0, 8, 16, 24]:
            m.d.comb += self.output[i : i + 8].eq(~self.intermediate[i : i + 8][::-1]) # Maybe the endianness is not entirely correct, not sure

        return m
