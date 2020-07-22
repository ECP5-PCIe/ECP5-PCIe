import itertools
from nmigen import *
from nmigen.build import *
from nmigen.hdl import Memory
from nmigen_stdio.serial import AsyncSerial
from nmigen_boards import versa_ecp5_5g as FPGA

__all__ = ["RP64PCIeInit"]

class RP64PCIeInit(Elaboratable):
    """Send 'pci init' to the ROCKPro64
    Parameters
    ----------
    rx : string
    tx : string
        RX and TX resource names
    rdy : Signal, out
        On when it is in the bootloader
    init : Signal, in
        Send init command
    init_sent : Signal, out
        Data to sample, 8 * words wide
    clk : int
        Clock frequency in Hertz
        
    """
    def __init__(self, rx, tx, rdy, init, init_sent, clk=1E8):
        self.rx = rx
        self.tx = tx
        self.rdy = rdy
        self.init = init
        self.init_sent = init_sent
        self.clk = clk

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        uart_pins = Record([("rx", [("i", 1)]), ("tx", [("o", 1)])])

        platform.add_resources([Resource("rx_rp64", 0, Pins(self.rx, dir="i"))])
        platform.add_resources([Resource("tx_rp64", 0, Pins(self.tx, dir="oe"))])

        rx_pin = platform.request("rx_rp64", 0)
        tx_pin = platform.request("tx_rp64", 0)

        m.d.comb += uart_pins.rx.i.eq(rx_pin.i)
        m.d.comb += tx_pin.o.eq(uart_pins.tx.o)

        enable_tx = Signal()
        m.d.comb += tx_pin.oe.eq(enable_tx)

        uart = AsyncSerial(divisor = int(self.clk / 1.5E6), pins = uart_pins)
        m.submodules += uart

        # Consider triggering reset and then waiting a second
        # Wait for 'Hit any key to stop autoboot:', minimally till 'Channel 0: LPDDR4, 50MHz', see https://gist.github.com/ECP5-PCIe/9343ca62714691de20075866d3306750 as an example.
        # Then set enable_tx to 1 and send '\n’ repeatingly, stop doing that at the next step.
        # When => arrives over the serial, assert rdy.
        # When init is 1, send 'pci enum\n' over serial.
        # As soon as the '\n' is sent, assert init_sent such that whatever uses this module is notified of that and can act (start logging SERDES data for example).

        # Turn a string into a list of bytes
        def generate_memory(data_string):
            result = []
            for char in data_string:
                result.append(ord(char))
            return result

        pci_mem = Memory(width = 8, depth = 9, init = generate_memory('pci enum\n'))
        pattern_match_mem = Memory(width = 8, depth = 19, init = generate_memory('Hit any key to stop'))
        pci_rport = m.submodules.pci_rport = pci_mem.read_port()


        m.d.comb += enable_tx.eq(1)
        timer = Signal(32)
        m.d.comb += uart.rx.rdy.eq(1)

        with m.FSM():
            with m.State("Wait"):
                m.d.sync += [
                    uart.tx.data.eq(0x03), # Spam Ctrl C
                    uart.tx.ack.eq(1),
                ]
                with m.If(uart.rx.data == ord('=')):
                    m.next = "uboot-1"

            with m.State("uboot-1"):
                with m.If(uart.rx.data == ord('>')):
                    m.next = "uboot-2"
                #with m.If(~((uart.rx.data == ord('>')) | (uart.rx.data == ord('=')))):
                #    m.next = "Wait"

            # Arrived at u-boot prompt
            with m.State("uboot-2"):
                m.d.sync += timer.eq(timer + 1)
                with m.If(timer == 100000000):
                    m.next = "send-pci-start" # Once a second send the sequence

            with m.State("send-pci-start"):
                m.d.sync += uart.tx.data.eq(pci_rport.data)
                m.d.sync += pci_rport.addr.eq(0)
                with m.If(uart.tx.ack):
                    m.next = "send-pci-data"

            with m.State("send-pci-data"):
                m.d.sync += uart.tx.data.eq(pci_rport.data)
                with m.If(uart.tx.ack):
                    m.d.sync += pci_rport.addr.eq(pci_rport.addr + 1)
                with m.If(pci_rport.addr == 8):
                    m.next = "uboot-2"
                    m.d.sync += timer.eq(0)


        uart_pins = platform.request("uart", 0)

        #m.d.comb += uart_pins.tx.o.eq(tx_pin.o)
        m.d.comb += uart_pins.tx.o.eq(rx_pin.i)

        return m

if (__name__ == "__main__"):
    FPGA.VersaECP55GPlatform().build(RP64PCIeInit("B18", "A18", Signal(), Signal(), Signal()), do_program=True, nextpnr_opts="--timing-allow-fail")