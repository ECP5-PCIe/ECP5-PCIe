from nmigen import *
from nmigen.build import *


__all__ = ["PLL", "PLL1Ch"]

class PLL(Elaboratable):
    def __init__(self, clkin, clksel=Signal(shape=2, reset=2), clkout1=Signal(), clkout2=Signal(), clkout3=Signal(), clkout4=Signal(), lock=Signal(), CLKI_DIV=1, CLKFB_DIV=1, CLK1_DIV=3, CLK2_DIV=4, CLK3_DIV=5, CLK4_DIV=6):
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
    def __init__(self, clkin, clkout=Signal(), lock=Signal(), CLKI_DIV=1, CLKFB_DIV=1, CLK_DIV=1):
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
