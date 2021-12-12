import itertools
from amaranth import *
from amaranth.build import *
from amaranth.hdl import Memory
from amaranth.hdl.ast import Rose, Fell
from amaranth_stdio.serial import AsyncSerial
from amaranth_boards import versa_ecp5_5g as FPGA

__all__ = ["RP64PCIeInit"]

class RP64PCIeInit(Elaboratable):
    """Send 'pci init' to the ROCKPro64 (RP64), start it before uploading anything to the ECP5, otherwise it wont boot. Connect a ground pin from the ECP5 to pin 6 on the RP64 Raspberry Pi (RPi)-like header
    Parameters
    ----------
    rx : string
        RX resource name, connect to pin 8 on the RP64 RPi-like header
    tx : string
        TX resource name, connect to pin 10 on the RP64 RPi-like header
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

        # UART pins for the AsyncSerial, is needed for doing output enable
        uart_pins = Record([("rx", [("i", 1)]), ("tx", [("o", 1)])])

        # Add the UART resources of the ROCKPro64
        platform.add_resources([Resource("rx_rp64", 0, Pins(self.rx, dir="i"))])
        platform.add_resources([Resource("tx_rp64", 0, Pins(self.tx, dir="oe"))])

        rx_pin = platform.request("rx_rp64", 0)
        tx_pin = platform.request("tx_rp64", 0)

        m.d.comb += uart_pins.rx.i.eq(rx_pin.i)
        m.d.comb += tx_pin.o.eq(uart_pins.tx.o)

        # ROCKPro64 refuses to boot if this is high
        enable_tx = Signal()
        m.d.comb += tx_pin.oe.eq(enable_tx)

        # 1.5 Megabaud UART to the ROCKPro64
        uart = AsyncSerial(divisor = int(self.clk / 1.5E6), pins = uart_pins)
        m.submodules += uart


        # Send 0x03 (Ctrl C) until the u-boot prompt appears (might take quite a while because apparently it seems to try to connect to the network interface for a long time)
        # Send 'pci enum' once '=>' is received and init is asserted
        # Set init_sent to high for 1 cycle after '\n' has been sent

        # Turn a string into a list of bytes
        def generate_memory(data_string):
            result = []
            for char in data_string:
                result.append(ord(char))
            return result

        # Command to send. Don't forget to change depth when changing this command.
        depth = 10
        pci_mem = Memory(width = 8, depth = depth, init = generate_memory(' pci enum\n'))
        pci_rport = m.submodules.pci_rport = pci_mem.read_port()

        # Hardwired to 1, since boot is not yet controlled
        m.d.comb += enable_tx.eq(1)

        # We can always accept data
        m.d.comb += uart.rx.ack.eq(1)

        with m.FSM():
            with m.State("Wait"):
                m.d.sync += [
                    uart.tx.data.eq(0x03), # Spam Ctrl C
                    uart.tx.ack.eq(1),
                ]

                # Wait for '=>'
                with m.If(uart.rx.data == ord('=')):
                    m.next = "uboot-1"

            with m.State("uboot-1"):
                m.d.sync += self.init_sent.eq(0)
                with m.If(uart.rx.data == ord('>')):
                    m.next = "uboot-2"

            # Arrived at u-boot prompt, ready to sent, waiting for init signal
            with m.State("uboot-2"):
                m.d.sync += self.rdy.eq(1)
                with m.If(self.init):
                    m.next = "send-pci-start"

            # Go! Set the UART data to what the memory outputs.
            with m.State("send-pci-start"):
                m.d.sync += [
                    self.rdy.eq(0),
                    uart.tx.data.eq(pci_rport.data),
                    pci_rport.addr.eq(0),
                ]

                # Once the TX is ready, send data
                with m.If(uart.tx.rdy):
                    m.next = "send-pci-data"

            with m.State("send-pci-data"):
                m.d.sync += uart.tx.data.eq(pci_rport.data)
                m.d.sync += uart.tx.ack.eq(uart.tx.rdy)

                # When the TX stops being ready, set the next byte. Doesn't work with 'Rose'.
                with m.If(Fell(uart.tx.rdy)):
                    m.d.sync += pci_rport.addr.eq(pci_rport.addr + 1)

                # Once all data has been sent, go back to waiting for '>' and strobe init_sent.
                with m.If((pci_rport.addr == depth - 1)):
                    m.next = "uboot-1"
                    m.d.sync += self.init_sent.eq(1)


        uart_pins = platform.request("uart", 0)

        #m.d.comb += uart_pins.tx.o.eq(tx_pin.o)
        m.d.comb += uart_pins.tx.o.eq(rx_pin.i)

        return m


if (__name__ == "__main__"):
    # Sends 'pci enum' in a loop
    # GND: X4 pin 2 -> RP64 RPi-like header pin 6 
    # RX : X4 pin 4 -> RP64 RPi-like header pin 8
    # TX : X4 pin 6 -> RP64 RPi-like header pin 10
    FPGA.VersaECP55GPlatform().build(RP64PCIeInit("A13", "C13", Signal(), 1, Signal()), do_program=True, nextpnr_opts="--timing-allow-fail")