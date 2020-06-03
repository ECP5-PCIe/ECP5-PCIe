from ecp5_serdes import LatticeECP5PCIeSERDES, PCIeSERDESAligner
from nmigen import *
from nmigen.build import *
from nmigen_boards import versa_ecp5_5g as FPGA

class Test(Elaboratable):
    def elaborate(self, platform):
        platform.add_resources([Resource("pcie_x1", 0,
        Subsignal("clk_p", Pins("Y11")),
        Subsignal("clk_n", Pins("Y12")),
        Subsignal("rx_p", Pins("Y5")),
        Subsignal("rx_n", Pins("Y6")),
        Subsignal("tx_p", Pins("W4")),
        Subsignal("tx_n", Pins("W5")),
        Subsignal("perst", Pins("A6"), Attrs(IO_TYPE="LVCMOS33")),
    )])

        m = Module()
        cd_serdes = ClockDomain()
        m.domains += cd_serdes
        serdes = LatticeECP5PCIeSERDES(platform.request("pcie_x1"))
        m.submodules += serdes
        aligner = DomainRenamer("rx")(PCIeSERDESAligner(serdes.lane)) # The lane
        m.submodules += aligner

        m.d.comb += [
            cd_serdes.clk.eq(serdes.rx_clk_o),
            serdes.rx_clk_i.eq(cd_serdes.clk),
            serdes.tx_clk_i.eq(cd_serdes.clk),

            aligner.rx_align.eq(1),
        ]

        return m

if __name__ == "__main__":
    FPGA.VersaECP55GPlatform().build(Test(), do_program=True)