import itertools
from nmigen import *
from nmigen.build import *
from nmigen.hdl import Memory
from nmigen_stdio.serial import AsyncSerial

__all__ = ["RP64PCIeInit"]

class RP64PCIeInit(Elaboratable):
    """Send 'pci init' to the RockPro64
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

        uart_pins = Record([("rx", 1), ("tx", 1)])

        platform.add_resources([Resource("rx_rp64", 0, Pins(self.rx, dir="i"))])
        platform.add_resources([Resource("tx_rp64", 0, Pins(self.tx, dir="oe"))])

        rx_pin = platform.request("rx_rp64", 0)
        tx_pin = platform.request("tx_rp64", 0)

        m.d.comb += uart_pins.rx.eq(rx_pin.i)
        m.d.comb += tx_pin.o.eq(uart_pins.tx)

        enable_tx = Signal()
        m.d.comb += tx_pin.oe.eq(enable_tx)

        uart = AsyncSerial(divisor = int(self.clk / 1.5E6), pins = uart_pins)
        m.submodules += uart

        # Wait for 'Hit any key to stop autoboot:', minimally till 'Channel 0: LPDDR4, 50MHz', see https://gist.github.com/ECP5-PCIe/9343ca62714691de20075866d3306750 as an example.
        # Then set enable_tx to 1 and send '\n’ repeatingly, stop doing that at the next step.
        # When => arrives over the serial, assert rdy.
        # When init is 1, send 'pci link\n' over serial.
        # As soon as the '\n' is sent, assert init_sent such that whatever uses this module is notified of that and can act (start logging SERDES data for example).

        # Turn a string into a list of bytes
        def generate_memory(data_string):
            result = []
            for char in data_string:
                result.append(ord(char))
            return result

        pci_link_mem = Memory(width = 8, depth = 9, init = generate_memory('pci link\n'))
        pattern_match_mem = Memory(width = 8, depth = 19, init = generate_memory('Hit any key to stop'))

        return





        uart = self.uart
        words = self.words
        depth = self.depth
        data = self.data
        if(self.timeout >= 0):
            timer = Signal(range(self.timeout + 1), reset=self.timeout)
        word_sel = Signal(range(2 * words), reset = 2 * words - 1)
        fifo = AsyncFIFOBuffered(width=8 * words, depth=depth, r_domain="sync", w_domain=self.data_domain)
        m.submodules += fifo

        m.d.comb += fifo.w_data.eq(data)

        def sendByteFSM(byte, nextState):
            sent = Signal(reset=0)
            with m.If(uart.tx.rdy):
                with m.If(sent == 0):
                    m.d.sync += uart.tx.data.eq(byte)
                    m.d.sync += uart.tx.ack.eq(1)
                    m.d.sync += sent.eq(1)
                with m.If(sent == 1):
                    m.d.sync += uart.tx.ack.eq(0)
                    m.d.sync += sent.eq(0)
                    m.next = nextState
        
        with m.FSM():
            with m.State("Wait"):
                m.d.sync += uart.rx.ack.eq(1)
                with m.If(uart.rx.rdy):
                    m.d.sync += uart.rx.ack.eq(0)
                    if self.timeout >= 0:
                        m.d.sync += timer.eq(self.timeout)
                    m.next = "Pre-Collect"
            with m.State("Pre-Collect"):
                sendByteFSM(ord('\n'), "Collect")
            with m.State("Collect"):
                with m.If(~fifo.w_rdy | ((timer == 0) if self.timeout >= 0 else 0)):
                    m.d.comb += fifo.w_en.eq(0)
                    m.next = "Transmit-1"
                with m.Else():
                    m.d.comb += fifo.w_en.eq(self.enable)
                    if self.timeout >= 0:
                        m.d.sync += timer.eq(timer - 1)
            with m.State("Transmit-1"):
                with m.If(fifo.r_rdy):
                    m.d.sync += fifo.r_en.eq(1)
                    m.next = "Transmit-2"
                with m.Else():
                    m.next = "Wait"
            with m.State("Transmit-2"):
                m.d.sync += fifo.r_en.eq(0)
                m.next = "TransmitByte"
            with m.State("TransmitByte"):
                sent = Signal(reset=0)
                with m.If(uart.tx.rdy):
                    with m.If(sent == 0):
                        hexNumber = HexNumber(fifo.r_data.word_select(word_sel, 4), Signal(8))
                        m.submodules += hexNumber
                        m.d.sync += uart.tx.data.eq(hexNumber.ascii)
                        m.d.sync += uart.tx.ack.eq(1)
                        m.d.sync += sent.eq(1)
                    with m.If(sent == 1):
                        m.d.sync += uart.tx.ack.eq(0)
                        m.d.sync += sent.eq(0)
                        with m.If(word_sel == 0):
                            m.d.sync += word_sel.eq(word_sel.reset)
                            m.next = "Separator"
                        with m.Else():
                            m.d.sync += word_sel.eq(word_sel - 1)
                with m.Else():
                    m.d.sync += uart.tx.ack.eq(0)
            with m.State("Separator"):
                sendByteFSM(ord('\n'), "Transmit-1")
        return m