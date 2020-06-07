from nmigen import *
from nmigen.build import *


__all__ = ["LatticeECP5PCIeSERDES"]


class LatticeECP5PCIeSERDES(Elaboratable):
    def __init__(self):
        self.refclk = Signal() # reference clock

        self.rxclk = Signal()  # recovered word clock
        self.rxdet = Signal()  # bit-align received data
        self.rxinv = Signal()  # invert received data
        self.rlos  = Signal()  # loss of signal
        self.rlol  = Signal()  # loss of lock
        self.rlsm  = Signal()  # link state machine up

        self.txclk = Signal()  # generated word clock
        self.tlol  = Signal()  # loss of lock

        self.rxbus = Signal(24)
        self.txbus = Signal(24)

        self.txd   = Signal(8)  # transmit data
        self.txk   = Signal()   # transmit comma
        self.txfd  = Signal()   # force disparity
        self.txds  = Signal()   # disparity

        self.rxd   = Signal(8)  # receive data
        self.rxk   = Signal()   # receive comma
        self.rxde  = Signal()   # disparity error
        self.rxce  = Signal()   # coding violation error
    
    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        m.submodules.extref0 = Instance("EXTREFB",
            o_REFCLKO=self.refclk,
            p_REFCK_PWDNB="0b1",
            p_REFCK_RTERM="0b1",            # 100 Ohm
            p_REFCK_DCBIAS_EN="0b0",
        )
        m.submodules.extref0.attrs["LOC"] = "EXTREF0"
        m.d.comb += Cat(self.rxd, self.rxk, self.rxde, self.rxce).eq(self.rxbus)
        m.d.comb += self.txbus.eq(Cat(self.txd, self.txk, self.txfd, self.txds))

        m.submodules.dcu0 = Instance("DCUA",
            # DCU — power management
            p_D_MACROPDB="0b1",
            p_D_IB_PWDNB="0b1",             # undocumented, seems to be "input buffer power down"
            p_D_TXPLL_PWDNB="0b1",
            i_D_FFC_MACROPDB=1,

            # DCU — reset
            i_D_FFC_MACRO_RST=0,
            i_D_FFC_DUAL_RST=0,
            i_D_FFC_TRST=0,

            # DCU — clocking
            i_D_REFCLKI=self.refclk,
            o_D_FFS_PLOL=self.tlol,
            p_D_REFCK_MODE="0b100",         # 25x REFCLK
            p_D_TX_MAX_RATE="2.5",          # 2.5 Gbps
            p_D_TX_VCO_CK_DIV="0b000",      # DIV/1
            p_D_BITCLK_LOCAL_EN="0b1",      # undocumented (PCIe sample code used)

            # DCU ­— unknown
            p_D_CMUSETBIASI="0b00",         # begin undocumented (PCIe sample code used)
            p_D_CMUSETI4CPP="0d4",
            p_D_CMUSETI4CPZ="0d3",
            p_D_CMUSETI4VCO="0b00",
            p_D_CMUSETICP4P="0b01",
            p_D_CMUSETICP4Z="0b101",
            p_D_CMUSETINITVCT="0b00",
            p_D_CMUSETISCL4VCO="0b000",
            p_D_CMUSETP1GM="0b000",
            p_D_CMUSETP2AGM="0b000",
            p_D_CMUSETZGM="0b100",
            p_D_SETIRPOLY_AUX="0b10",
            p_D_SETICONST_AUX="0b01",
            p_D_SETIRPOLY_CH="0b10",
            p_D_SETICONST_CH="0b10",
            p_D_SETPLLRC="0d1",
            p_D_RG_EN="0b1",
            p_D_RG_SET="0b00",              # end undocumented

            # DCU — FIFOs
            p_D_LOW_MARK="0d4",
            p_D_HIGH_MARK="0d12",

            # CH0 — protocol
            p_CH0_PROTOCOL="PCIE",
            p_CH0_PCIE_MODE="0b1",

            # RX CH ­— power management
            p_CH0_RPWDNB="0b1",
            i_CH0_FFC_RXPWDNB=1,

            # RX CH ­— reset
            i_CH0_FFC_RRST=0,
            i_CH0_FFC_LANE_RX_RST=0,

            # RX CH ­— input
            i_CH0_FFC_SB_INV_RX=self.rxinv,

            p_CH0_RTERM_RX="0d22",          # 50 Ohm (wizard value used, does not match datasheet)
            p_CH0_RXIN_CM="0b11",           # CMFB (wizard value used)
            p_CH0_RXTERM_CM="0b11",         # RX Input (wizard value used)

            # RX CH ­— clocking
            i_CH0_RX_REFCLK=self.refclk,
            o_CH0_FF_RX_PCLK=self.rxclk,
            i_CH0_FF_RXI_CLK=self.rxclk,

            p_CH0_AUTO_FACQ_EN="0b1",       # undocumented (wizard value used)
            p_CH0_AUTO_CALIB_EN="0b1",      # undocumented (wizard value used)
            p_CH0_CDR_MAX_RATE="2.5",       # 2.5 Gbps
            p_CH0_RX_DCO_CK_DIV="0b000",    # DIV/1
            p_CH0_PDEN_SEL="0b1",           # phase detector disabled on LOS
            p_CH0_SEL_SD_RX_CLK="0b1",      # FIFO driven by recovered clock
            p_CH0_CTC_BYPASS="0b1",         # bypass CTC FIFO

            p_CH0_DCOATDCFG="0b00",         # begin undocumented (PCIe sample code used)
            p_CH0_DCOATDDLY="0b00",
            p_CH0_DCOBYPSATD="0b1",
            p_CH0_DCOCALDIV="0b010",
            p_CH0_DCOCTLGI="0b011",
            p_CH0_DCODISBDAVOID="0b1",
            p_CH0_DCOFLTDAC="0b00",
            p_CH0_DCOFTNRG="0b010",
            p_CH0_DCOIOSTUNE="0b010",
            p_CH0_DCOITUNE="0b00",
            p_CH0_DCOITUNE4LSB="0b010",
            p_CH0_DCOIUPDNX2="0b1",
            p_CH0_DCONUOFLSB="0b101",
            p_CH0_DCOSCALEI="0b01",
            p_CH0_DCOSTARTVAL="0b010",
            p_CH0_DCOSTEP="0b11",           # end undocumented

            # RX CH — link state machine
            i_CH0_FFC_SIGNAL_DETECT=self.rxdet,
            o_CH0_FFS_LS_SYNC_STATUS=self.rlsm,
            p_CH0_ENABLE_CG_ALIGN="0b1",
            p_CH0_UDF_COMMA_MASK="0x3ff",   # compare all 10 bits
            p_CH0_UDF_COMMA_A="0x283",      # K28.5 inverted
            p_CH0_UDF_COMMA_B="0x17C",      # K28.5

            p_CH0_MIN_IPG_CNT="0b11",       # minimum interpacket gap of 4
            p_CH0_MATCH_4_ENABLE="0b1",     # 4 character skip matching
            p_CH0_CC_MATCH_1="0x1BC",       # K28.5
            p_CH0_CC_MATCH_2="0x11C",       # K28.0
            p_CH0_CC_MATCH_3="0x11C",       # K28.0
            p_CH0_CC_MATCH_4="0x11C",       # K28.0

            # RX CH — loss of signal
            o_CH0_FFS_RLOS=self.rlos,
            p_CH0_RLOS_SEL="0b1",
            p_CH0_RX_LOS_EN="0b1",
            p_CH0_RX_LOS_LVL="0b100",       # Lattice "TBD" (wizard value used)
            p_CH0_RX_LOS_CEQ="0b11",        # Lattice "TBD" (wizard value used)

            # RX CH — loss of lock
            o_CH0_FFS_RLOL=self.rlol,

            # RX CH — data
            **{"o_CH0_FF_RX_D_%d" % n: self.rxbus[n] for n in range(self.rxbus.width)},
            p_CH0_DEC_BYPASS="0b0",

            # TX CH — power management
            p_CH0_TPWDNB="0b1",
            i_CH0_FFC_TXPWDNB=1,

            # TX CH ­— reset
            i_CH0_FFC_LANE_TX_RST=0,

            # TX CH ­— output

            p_CH0_TXAMPLITUDE="0d1000",     # 1000 mV
            p_CH0_RTERM_TX="0d19",          # 50 Ohm

            p_CH0_TDRV_SLICE0_CUR="0b011",  # 400 uA
            p_CH0_TDRV_SLICE0_SEL="0b01",   # main data
            p_CH0_TDRV_SLICE1_CUR="0b000",  # 100 uA
            p_CH0_TDRV_SLICE1_SEL="0b00",   # power down
            p_CH0_TDRV_SLICE2_CUR="0b11",   # 3200 uA
            p_CH0_TDRV_SLICE2_SEL="0b01",   # main data
            p_CH0_TDRV_SLICE3_CUR="0b11",   # 3200 uA
            p_CH0_TDRV_SLICE3_SEL="0b01",   # main data
            p_CH0_TDRV_SLICE4_CUR="0b11",   # 3200 uA
            p_CH0_TDRV_SLICE4_SEL="0b01",   # main data
            p_CH0_TDRV_SLICE5_CUR="0b00",   # 800 uA
            p_CH0_TDRV_SLICE5_SEL="0b00",   # power down

            # TX CH ­— clocking
            o_CH0_FF_TX_PCLK=self.txclk,
            i_CH0_FF_TXI_CLK=self.txclk,

            # TX CH — data
            **{"o_CH0_FF_TX_D_%d" % n: self.txbus[n] for n in range(self.txbus.width)},
            p_CH0_ENC_BYPASS="0b0",
        )
        m.submodules.dcu0.attrs["LOC"] = "DCU0"
        m.submodules.dcu0.attrs["CHAN"] = "CH0"
        m.submodules.dcu0.attrs["BEL"] = "X42/Y71/DCU"
        return m