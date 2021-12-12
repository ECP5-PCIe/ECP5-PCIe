from amaranth import *
from amaranth.build import *


__all__ = ["PLL", "PLL1Ch", "DTR"]

class PLL(Elaboratable):
    def __init__(self, clkin, clksel, clkout1, clkout2, clkout3, clkout4, lock, CLKI_DIV=1, CLKFB_DIV=1, CLK1_DIV=3, CLK2_DIV=4, CLK3_DIV=5, CLK4_DIV=6):
        self.clkin = clkin
        self.clkout1 = clkout1
        self.clkout2 = clkout2
        self.clkout3 = clkout3
        self.clkout4 = clkout4
        self.clksel = clksel
        self.lock = lock
        self.CLKI_DIV = CLKI_DIV
        self.CLKFB_DIV = CLKFB_DIV
        self.CLKOP_DIV = CLK1_DIV
        self.CLKOS_DIV = CLK2_DIV
        self.CLKOS2_DIV = CLK3_DIV
        self.CLKOS3_DIV = CLK4_DIV
        self.ports = [
            self.clkin,
            self.clkout1,
            self.clkout2,
            self.clkout3,
            self.clkout4,
            self.clksel,
            self.lock,
        ]

    def elaborate(self, platform):
        clkfb = Signal()
        pll = Instance("EHXPLLL",
            p_PLLRST_ENA='DISABLED',
            p_INTFB_WAKE='DISABLED',
            p_STDBY_ENABLE='DISABLED',
            p_CLKOP_FPHASE=0,
            p_CLKOP_CPHASE=11,
            p_OUTDIVIDER_MUXA='DIVA',
            p_CLKOP_ENABLE='ENABLED',
            p_CLKOP_DIV=self.CLKOP_DIV, #Max 948 MHz at OP=79 FB=1 I=1 F_in=12 MHz, Min 30 MHz (28 MHz locks sometimes, lock LED blinks) Hmm... /3*82/25
            p_CLKOS_DIV=self.CLKOS_DIV,
            p_CLKOS2_DIV=self.CLKOS2_DIV,
            p_CLKOS3_DIV=self.CLKOS3_DIV,
            p_CLKFB_DIV=self.CLKFB_DIV, #25
            p_CLKI_DIV=self.CLKI_DIV, #6
            p_FEEDBK_PATH='USERCLOCK',
            i_CLKI=self.clkin,
            i_CLKFB=clkfb,
            i_RST=0,
            i_STDBY=0,
            i_PHASESEL0=0,
            i_PHASESEL1=0,
            i_PHASEDIR=0,
            i_PHASESTEP=0,
            i_PLLWAKESYNC=0,
            i_ENCLKOP=0,
            i_ENCLKOS=0,
            i_ENCLKOS2=0,
            i_ENCLKOS3=0,
            o_CLKOP=self.clkout1,
            o_CLKOS=self.clkout2,
            o_CLKOS2=self.clkout3,
            o_CLKOS3=self.clkout4,
            o_LOCK=self.lock,
            #o_LOCK=pll_lock
            )
        m = Module()
        m.submodules += pll
        with m.If(self.clksel == 0):
            m.d.comb += clkfb.eq(self.clkout1)
        with m.Elif(self.clksel == 1):
            m.d.comb += clkfb.eq(self.clkout2)
        with m.Elif(self.clksel == 2):
            m.d.comb += clkfb.eq(self.clkout3)
        with m.Else():
            m.d.comb += clkfb.eq(self.clkout4)
        return m

class PLL1Ch(Elaboratable):
    def __init__(self, clkin, clkout, lock, CLKI_DIV=1, CLKFB_DIV=1, CLK_DIV=1):
        self.clkin = clkin
        self.clkout = clkout
        self.lock = lock
        self.CLKI_DIV = CLKI_DIV
        self.CLKFB_DIV = CLKFB_DIV
        self.CLKOP_DIV = CLK_DIV
        self.ports = [
            self.clkin,
            self.clkout,
            self.lock,
        ]

    def elaborate(self, platform):
        pll = Instance("EHXPLLL",
            p_PLLRST_ENA='DISABLED',
            p_INTFB_WAKE='DISABLED',
            p_STDBY_ENABLE='DISABLED',
            p_CLKOP_FPHASE=0,
            p_CLKOP_CPHASE=11,
            p_OUTDIVIDER_MUXA='DIVA',
            p_CLKOP_ENABLE='ENABLED',
            p_CLKOP_DIV=self.CLKOP_DIV, #Max 948 MHz at OP=79 FB=1 I=1 F_in=12 MHz, Min 30 MHz (28 MHz locks sometimes, lock LED blinks) Hmm... /3*82/25
            p_CLKFB_DIV=self.CLKFB_DIV, #25
            p_CLKI_DIV=self.CLKI_DIV, #6
            p_FEEDBK_PATH='CLKOP',
            i_CLKI=self.clkin,
            i_CLKFB=self.clkout,
            i_RST=0,
            i_STDBY=0,
            i_PHASESEL0=0,
            i_PHASESEL1=0,
            i_PHASEDIR=0,
            i_PHASESTEP=0,
            i_PLLWAKESYNC=0,
            i_ENCLKOP=1,
            o_CLKOP=self.clkout,
            o_LOCK=self.lock,
            #o_LOCK=pll_lock
            )
        m = Module()
        m.submodules += pll
        return m

class DTR(Elaboratable):
    # See TN1266
    CONVERSION_TABLE = [-58, -56, -54, -52, -45, -44, -43, -42, -41, -40, -39, -38, -37, -36, -30, -20, -10, -4, 0, 4, 10, 21, 22, 23, 24, 25, 26, 27, 28, 29, 40, 50, 60, 70, 76, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 116, 120, 124, 128, 132]

    def __init__(self, start = None, temperature = None, valid = None):
        self.start = Signal() if start is None else start
        self.temperature = Signal(6) if temperature is None else temperature
        self.valid = Signal() if valid is None else valid

    def elaborate(self, platform):
        m = Module()

        dtrout = Signal(8)

        m.submodules += Instance("DTR",
            i_STARTPULSE=self.start,
            **{"o_DTROUT%d" % n: dtrout[n] for n in range(8)},
            )
        
        m.d.comb += self.valid.eq(dtrout[7])
        m.d.comb += self.temperature.eq(dtrout[0:6])

        return m
