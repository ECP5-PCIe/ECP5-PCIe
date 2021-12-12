from amaranth import *
from amaranth.build import *


__all__ = ["ECP5SerDesConfigInterface", "ECP5SerDesConfigController"]



class ECP5SerDesConfigInterface(Elaboratable): # Copied from LUNA, https://github.com/greatscottgadgets/luna/blob/main/luna/gateware/interface/serdes_phy/backends/ecp5.py
    """ Module that interfaces with the ECP5's SerDes Client Interface (SCI). """

    def __init__(self):
        #
        # I/O port
        #

        # Control interface.
        self.dual_sel = Signal()
        self.chan_sel = Signal()
        self.re       = Signal()
        self.we       = Signal()
        self.done     = Signal()
        self.adr      = Signal(6)
        self.dat_w    = Signal(8)
        self.dat_r    = Signal(8)

        # SCI interface.
        self.sci_rd    = Signal()
        self.sci_wrn   = Signal()
        self.sci_addr  = Signal(6)
        self.sci_wdata = Signal(8)
        self.sci_rdata = Signal(8)



    def elaborate(self, platform):
        m = Module()

        m.d.comb += [
            self.sci_wrn.eq(1),

            self.sci_addr.eq(self.adr),
            self.sci_wdata.eq(self.dat_w)
        ]

        with m.FSM(domain="sync"):

            with m.State("IDLE"):
                m.d.comb += self.done.eq(1)

                with m.If(self.we):
                    m.next = "WRITE"
                with m.Elif(self.re):
                    m.d.comb += self.sci_rd.eq(1),
                    m.next = "READ"

            with m.State("WRITE"):
                m.d.comb += self.sci_wrn.eq(0)
                m.next = "IDLE"


            with m.State("READ"):
                m.d.comb += self.sci_rd.eq(1)
                m.d.sync += self.dat_r.eq(self.sci_rdata)
                m.next = "IDLE"

        return m



class ECP5SerDesConfigController(Elaboratable): # Copied from LUNA, https://github.com/greatscottgadgets/luna/blob/main/luna/gateware/interface/serdes_phy/backends/ecp5.py
    """
    Controller for the ECP5 SerDes Client Interface (SCI).

    Parameters
    ----------
    sci : ECP5SerDesConfigInterface
        SCI interface to use
    vals_ch_write : [[reg : int, val : string]]
        Value to write at register reg in channel registers.
        val is an 8 bit value.
        Use - in string to specify bits to not touch.
        For example: "11-----0"
    vals_du_write : [[reg : int, val : string]]
        Value to write in DCU registers, see vals_ch_write
    vals_ch_read : [[reg : int, sig : Signal]]
        Read value at channel register reg into signal sig
    vals_du_read : [[reg : int, sig : Signal]]
        Read value at DCU register reg into signal sig
    """

    def __init__(self, sci, vals_ch_write=[], vals_du_write=[], vals_ch_read=[], vals_du_read=[]):
        self.sci            = sci
        self.vals_ch_write  = vals_ch_write
        self.vals_du_write  = vals_du_write
        self.vals_ch_read   = vals_ch_read
        self.vals_du_read   = vals_du_read



    def elaborate(self, platform):
        m = Module()

        sci            = self.sci
        vals_ch_write  = self.vals_ch_write
        vals_du_write  = self.vals_du_write
        vals_ch_read   = self.vals_ch_read
        vals_du_read   = self.vals_du_read

        # TODO: Find better solution
        if len(vals_ch_write) == 0:
            vals_ch_write = [[-1]]

        if len(vals_du_write) == 0:
            vals_du_write = [[-1]]

        if len(vals_ch_read) == 0:
            vals_ch_read = [[-1]]

        if len(vals_du_read) == 0:
            vals_du_read = [[-1]]


        data = Signal(8)
        first = Signal()


        # TODO: Make this less redundant
        with m.FSM(domain="sync"):
            # Procedurally generate FSM
            for i in range(len(vals_ch_write)):
                ch = vals_ch_write[i][0]

                # If there are no channels to write to skip it
                if ch == -1:
                    with m.State("READ-CH_" + hex(ch)):
                        m.next = "READ-DU_" + hex(vals_du_write[0][0])

                else:
                    with m.State("READ-CH_" + hex(ch)):
                        m.d.sync += first.eq(0)
                        m.d.comb += [
                            sci.chan_sel.eq(1), # Select channel registers
                            sci.dual_sel.eq(0),
                            sci.re.eq(1),
                            sci.adr.eq(ch),
                        ]

                        with m.If(~first & sci.done):
                            m.d.comb += sci.re.eq(0)
                            m.d.sync += [
                                data.eq(sci.dat_r), # Read channel to data signal
                                first.eq(1),
                            ]
                            m.next = "WRITE-CH_" + hex(ch)

                    with m.State("WRITE-CH_" + hex(ch)):
                        m.d.sync += first.eq(0)
                        m.d.comb += [
                            sci.chan_sel.eq(1),
                            sci.dual_sel.eq(0),
                            sci.we.eq(1),
                            sci.adr.eq(ch),
                            sci.dat_w.eq(data),
                        ]

                        for j in range(len(vals_ch_write[i][1])):
                            c = vals_ch_write[i][1][j]
                            if c != "-": # Only overwrite bits which should be overridden (thats why we read the channel before)
                                m.d.comb += sci.dat_w[j].eq(int(c))

                        with m.If(~first & sci.done):
                            m.d.comb += sci.we.eq(0)
                            m.d.sync += first.eq(1)
                            if i + 1 == len(vals_ch_write):
                                m.next = "READ-DU_" + hex(vals_du_write[0][0])
                            else:
                                m.next = "READ-CH_" + hex(vals_ch_write[i + 1][0])

            for i in range(len(vals_du_write)):
                dl = vals_du_write[i][0]

                if dl == -1:
                    with m.State("READ-DU_" + hex(dl)):
                        m.next = "READ-VAL-CH_" + hex(vals_ch_read[0][0])

                else:
                    with m.State("READ-DU_" + hex(dl)):
                        m.d.sync += first.eq(0)
                        m.d.comb += [
                            sci.chan_sel.eq(0),
                            sci.dual_sel.eq(1),
                            sci.re.eq(1),
                            sci.adr.eq(dl),
                        ]

                        with m.If(sci.done):
                            m.d.comb += sci.re.eq(0)
                            m.d.sync += [
                                data.eq(sci.dat_r),
                                first.eq(1),
                            ]
                            m.next = "WRITE-DU_" + hex(dl)

                    with m.State("WRITE-DU_" + hex(dl)):
                        m.d.sync += first.eq(0)
                        m.d.comb += [
                            sci.chan_sel.eq(0),
                            sci.dual_sel.eq(1),
                            sci.we.eq(1),
                            sci.adr.eq(dl),
                            sci.dat_w.eq(data),
                        ]

                        for j in range(len(vals_du_write[i][1])):
                            c = vals_du_write[i][1][j]
                            if c != "-":
                                m.d.comb += sci.dat_w[j].eq(int(c))

                        with m.If(~first & sci.done):
                            m.d.comb += sci.we.eq(0)
                            m.d.sync += first.eq(1)
                            if i + 1 == len(vals_du_write):
                                m.next = "READ-VAL-CH_" + hex(vals_ch_write[0][0])
                            else:
                                m.next = "READ-DU_" + hex(vals_du_write[i + 1][0])

            for i in range(len(vals_ch_read)):
                ch = vals_ch_read[i][0]

                if ch == -1:
                    with m.State("READ-VAL-CH_" + hex(ch)):
                        m.next = "READ-VAL-DU_" + hex(vals_du_read[0][0])

                else:
                    with m.State("READ-VAL-CH_" + hex(ch)):
                        m.d.sync += first.eq(0)
                        m.d.comb += [
                            sci.chan_sel.eq(1),
                            sci.dual_sel.eq(0),
                            sci.re.eq(1),
                            sci.adr.eq(ch),
                        ]

                        with m.If(~first & sci.done):
                            m.d.comb += sci.re.eq(0)
                            m.d.sync += [
                                vals_ch_read[i][1].eq(sci.dat_r), # Read to signal
                                first.eq(1),
                            ]
                            if i + 1 == len(vals_ch_read):
                                m.next = "READ-VAL-DU_" + hex(vals_du_read[0][0])
                            else:
                                m.next = "READ-VAL-CH_" + hex(vals_ch_read[i + 1][0])

            for i in range(len(vals_du_read)):
                dl = vals_du_read[i][0]

                if dl == -1:
                    with m.State("READ-VAL-DU_" + hex(dl)):
                        m.next = "READ-CH_" + hex(vals_ch_write[0][0])

                else:
                    with m.State("READ-VAL-DU_" + hex(dl)):
                        m.d.sync += first.eq(0)
                        m.d.comb += [
                            sci.chan_sel.eq(0),
                            sci.dual_sel.eq(1),
                            sci.re.eq(1),
                            sci.adr.eq(dl),
                        ]

                        with m.If(sci.done):
                            m.d.comb += sci.re.eq(0)
                            m.d.sync += [
                                vals_du_read[i][1].eq(sci.dat_r),
                                first.eq(1),
                            ]
                            if i + 1 == len(vals_du_read):
                                m.next = "READ-CH_" + hex(vals_ch_write[0][0])
                            else:
                                m.next = "READ-VAL-DU_" + hex(vals_du_read[i + 1][0])


        return m