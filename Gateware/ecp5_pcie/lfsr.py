from nmigen import *
from nmigen.build import *


__all__ = ["PCIeLFSR"]


class PCIeLFSR(Elaboratable):
    """
    PCIe Linear Feedback Shift Register for scrambling

    Parameters
    ----------
    bytes : int
        Number of bytes of scrambling data to produce
    reset : Signal
        Reset LFSR, should be 'symbol == Ctrl.COM'
    advance : Signal
        Advance LFSR, should be 'symbol != Ctrl.SKP'
    
    output : Signal(9 * bytes)
        output data for scrambling. XOR symbols with this to scramble. 9th bit is 0
    """
    def __init__(self, bytes, reset = Signal(), advance = Signal()):
        self.reset = reset
        self.advance = advance
        self.output = Signal(9 * bytes)
        #self.count = Signal(32)
        self.__bytes = bytes

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        #def calculate_lfsr(advances):
        #    state = 0xFFFF
        #    for _ in range(advances):
        #        state = ((state >> 8) | ((state & 0xFF) << 8)) ^ ((state & 0xFF00) >> 5) ^ ((state & 0xFF00) >> 4) ^ ((state & 0xFF00) >> 3)
        #    return state

        def apply_lfsr(in_state):
            return Cat(in_state[8:16], in_state[0:8]) ^ Cat(Const(0, 3), in_state[8:16]) ^ Cat(Const(0, 4), in_state[8:16]) ^ Cat(Const(0, 5), in_state[8:16])

        #states = [Signal(16, reset=calculate_lfsr(i)) for i in range(self.__bytes)]
        states = [Signal(16, reset=0xFFFF) for i in range(self.__bytes)]# * self.__bytes

        with m.If(self.advance):
            with m.If(self.reset):
                for i in range(self.__bytes):
                    m.d.rx += states[0].eq(0xFFFF)
            with m.Else():
                for i in range(self.__bytes):
                    if i == self.__bytes - 1:
                        m.d.rx += states[0].eq(apply_lfsr(states[i]))
                    else:
                        m.d.comb += states[i + 1].eq(apply_lfsr(states[i]))
        
        for i in range(self.__bytes):
            m.d.comb += self.output.word_select(i, 9).eq(states[i][15:7:-1])

        return m