import itertools
from amaranth import *
from amaranth.build import *
from amaranth.lib.fifo import AsyncFIFOBuffered

__all__ = ["Sequencer", "FunctionSequencer", "LFSR", "Resizer", "Rotator", "HexNumber", "UARTDebugger"]

class Sequencer(Elaboratable): # Does signal.eq(value) where values is a 2D array, values[m] being the values for the mth signal and values[m][n] being the values for the mth signal at the nth step. times is the clock cycle number of each occurence
    def __init__(self, signals, values, done, reset, times=lambda x : x):
        self.signals = signals
        self.values = values
        self.reset = reset
        self.done = done
        self.times = times
        self.ports = [
            self.signals,
            self.reset,
            self.done,
        ]
        len0 = len(values[0])
        self.length = len0
        for row in values:
            assert len(row) == len0

    def elaborate(self, platform):
        m = Module()
        maxT = 0
        for i in range(0, self.length):
            maxT = max(maxT, self.times[i])
        
        counter = Signal(range(maxT + 1), reset=maxT)
        
        for i in range(0, self.length):
            with m.If(counter == int(self.times[i])):
                for j in range(0, len(self.signals)):
                    m.d.sync += self.signals[j].eq(self.values[j][i])
        
        with m.If(counter < maxT):
            m.d.sync += counter.eq(counter + 1)
            m.d.comb += self.done.eq(0)
        with m.If(counter == maxT):
            m.d.comb += self.done.eq(1)
            with m.If(self.reset == 1):
                m.d.sync += counter.eq(0)
        return m

class FunctionSequencer(Elaboratable): # Does signal.eq(value) where points is list of tuples, functions[n][0] being the time in clock cycles when the function is executed and functions[n][1] being the function executed at the nth step on sync domain. times is the clock cycle number of each occurence
    def __init__(self, points, done, reset, startByDefault=False):
        self.points = points
        self.reset = reset
        self.startByDefault = startByDefault
        self.done = done
        self.ports = [
            self.reset,
            self.done,
        ]
        self.length = len(points)

    def elaborate(self, platform):
        m = Module()
        maxT = 0
        for i in range(0, self.length):
            maxT = max(maxT, self.points[i][0])
        
        counter = Signal(range(maxT + 1), reset=0 if self.startByDefault else maxT)
        
        for i in range(0, self.length):
            with m.If(counter == int(self.points[i][0])):
                m.d.sync += self.points[i][1]
        
        with m.If(counter < maxT):
            m.d.sync += counter.eq(counter + 1)
            m.d.comb += self.done.eq(0)
        with m.If(counter == maxT):
            m.d.comb += self.done.eq(1)
            with m.If(self.reset == 1):
                m.d.sync += counter.eq(0)
        return m

class LFSR(Elaboratable):
    def __init__(self, out, domain="sync", taps=[25,16,14,13,11], run=1, reset=1, skip = 0):
        self.out = out
        self.taps = taps
        self.run = run
        self.reset = reset
        self.domain = domain
        self.skip = skip
        self.ports = [
            self.out,
            self.run,
        ]

    def elaborate(self, platform):
        m = Module()
        
        skipLFSR = self.reset
        for i in range(0, self.skip):
            skipLFSR = skipLFSR << 1 #Order may be wrong
            val = 0
            for tap in self.taps:
                val ^= (skipLFSR >> tap) & 1 == 1
            skipLFSR += val
        
        lfsr = Signal(max(self.taps) + 1, reset=skipLFSR & ((1 << (max(self.taps) + 1)) - 1))
        m.d.comb += self.out.eq(lfsr[0])
        sig0 = lfsr[self.taps[0]]
        
        for tap in self.taps[1:]:
            sig0 ^= lfsr[tap]
        
        with m.If(self.run):
            m.d[self.domain] += lfsr.eq(lfsr << 1) #Order may be wrong
            m.d[self.domain] += lfsr[0].eq(sig0)
        
        return m

class Resizer(Elaboratable):
    def __init__(self, datain, dataout, datastep, enable=1): #datastep toggled for 1 cycle when new data is there when enlarging or when new data needs to be sampled when shrinking.
        if len(datain) > len(dataout):
            assert len(datain) % len(dataout) == 0
            self.enlarge = False
            self.ratio = int(len(datain) / len(dataout))
            self.step = len(dataout)
        else:
            assert len(dataout) % len(datain) == 0
            self.enlarge = True
            self.ratio = int(len(dataout) / len(datain))
            self.step = len(datain)
        
        self.datain = datain
        self.dataout = dataout
        self.enable = enable
        self.datastep = datastep
        self.ports = [
            self.datain,
            self.dataout,
            self.enable,
            self.datastep,
        ]

    def elaborate(self, platform):
        m = Module()
        
        datain = self.datain
        dataout = self.dataout
        step = self.step
        ratio = self.ratio
        datastep = self.datastep
        counter = Signal(range(ratio))
        databuf = Signal(len(dataout))
        with m.If(self.enable == 1):
            with m.If(counter >= ratio - 1):
                m.d.sync += counter.eq(0)
                m.d.comb += datastep.eq(1) #Try to put in sync without error
                if self.enlarge:
                    m.d.sync += dataout.eq(databuf)
            with m.Else():
                m.d.sync += counter.eq(counter + 1)
                m.d.comb += datastep.eq(0)
            if self.enlarge:
                m.d.sync += databuf.word_select(counter, step).eq(datain)
            else:
                m.d.sync += dataout.eq(datain.word_select(counter, step))
        with m.Else():
            m.d.comb += datastep.eq(0)
        return m

class Rotator(Elaboratable):
    def __init__(self, datain, dataout, rotation=0, comb=True):
        assert len(datain) == len(dataout)
        
        self.datain = datain
        self.dataout = dataout
        self.rotation = rotation
        self.comb = comb
        
        self.ports = [
            self.datain,
            self.dataout,
            self.rotation,
        ]

    def elaborate(self, platform):
        m = Module()
        
        length = len(self.datain)
        with m.Switch(self.rotation):
            for i in range(length):
                with m.Case(i):
                    if self.comb:
                        m.d.comb += self.dataout.eq(Cat(self.datain[i:length], self.datain[0:i]))
                    else:
                        m.d.sync += self.dataout.eq(Cat(self.datain[i:length], self.datain[0:i]))
        
        return m

class HexNumber(Elaboratable):
    def __init__(self, data, ascii, comb=True):
        assert len(data) == 4
        assert len(ascii) == 8
        
        self.data = data
        self.ascii = ascii
        self.comb = comb
        
        self.ports = [
            self.data,
            self.ascii,
        ]

    def elaborate(self, platform):
        m = Module()
        
        with m.Switch(self.data):
            for i in range(0, 10):
                with m.Case(i):
                    if self.comb:
                        m.d.comb += self.ascii.eq(ord('0') + self.data)
                    else:
                        m.d.sync += self.ascii.eq(ord('0') + self.data)
            for i in range(10, 16):
                with m.Case(i):
                    if self.comb:
                        m.d.comb += self.ascii.eq(ord('A') + self.data - 10)
                    else:
                        m.d.sync += self.ascii.eq(ord('A') + self.data - 10)
        
        return m

class UARTDebugger(Elaboratable):
    """UART Debugger. Once a symbol comes in over the UART, it records data in a FIFO at sync rate and then sends them over UART.
    Parameters
    ----------
    uart : AsyncSerial
        UART interface from amaranth_stdio
    words : int
        Number of bytes
    depth : int
        Number of samples stored in FIFO
    data : Signal, in
        Data to sample, 8 * words wide
    data_domain : string
        Input clock domain
    enable : Signal, in
        Enable sampling
        
    """
    def __init__(self, uart, words, depth, data, data_domain="sync", enable=1, timeout=-1):
        assert(len(data) == words * 8)
        self.uart = uart
        self.words = words
        self.depth = depth
        self.data = data
        self.data_domain = data_domain
        self.enable = enable
        self.timeout = timeout

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

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

class UARTDebugger2(Elaboratable):
    """UART Debugger. It records data in a FIFO at sync rate and once a symbol comes in over the UART it sends the FIFO contents over UART.
    Parameters
    ----------
    uart : AsyncSerial
        UART interface from amaranth_stdio
    words : int
        Number of bytes
    depth : int
        Number of samples stored in FIFO
    data : Signal, in
        Data to sample, 8 * words wide
    data_domain : string
        Input clock domain
    enable : Signal, in
        Enable sampling
        
    """
    def __init__(self, uart, words, depth, data, data_domain="sync", enable=1, timeout=-1):
        assert(len(data) == words * 8)
        self.uart = uart
        self.words = words
        self.depth = depth
        self.data = data
        self.data_domain = data_domain
        self.enable = enable
        self.timeout = timeout

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

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
            with m.State("Collect"):
                with m.If(~fifo.w_rdy | ((timer == 0) if self.timeout >= 0 else 0)):
                    m.d.comb += fifo.w_en.eq(0)
                    m.next = "Wait"
                with m.Else():
                    m.d.comb += fifo.w_en.eq(self.enable)
                    if self.timeout >= 0:
                        m.d.sync += timer.eq(timer - 1)

            with m.State("Wait"):
                m.d.sync += uart.rx.ack.eq(1)
                with m.If(uart.rx.rdy):
                    m.d.sync += uart.rx.ack.eq(0)
                    if self.timeout >= 0:
                        m.d.sync += timer.eq(self.timeout)
                    m.next = "Pre-Transmit"

            with m.State("Pre-Transmit"):
                sendByteFSM(ord('\n'), "Transmit-1")

            with m.State("Transmit-1"):
                with m.If(fifo.r_rdy):
                    m.d.sync += fifo.r_en.eq(1)
                    m.next = "Transmit-2"
                with m.Else():
                    m.next = "Collect"

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

            with m.State("TransmitEnd"):
                sendByteFSM(ord('Z'), "Collect")
        return m

class __UARTDebuggerWrapper: # Not really usable, amaranth part of Gateware needs to be executed to determine signal sizes for this to be usable (and the read function isn't finished).
    """UART Debugger Wrapper. It wraps an UARTDebugger2 for ease of use.
    Parameters
    ----------
    depth : int
        Maximum number of samples stored in the FIFO buffer
    """
    def __init__(self, depth):
        assert(len(data) == words * 8)
        self.depth = depth
    
    """Initialize FPGA side, add return value of this function as a submodule
    Parameters
    ----------
    uart : AsyncSerial
        UART interface from amaranth_stdio
    data : Dictionary of Name, Signal, in
        Data to sample
    data_domain : string
        Input clock domain
    enable : Signal, in
        Enable sampling
    """
    def init_fpga(self, uart, data, data_domain="sync", enable=1, timeout=-1):
        current_bit = 0
        data_format = [] # Array of [name, position, length]
        signals     = [] # Signals to Cat

        for key, value in data:
            data_format.append([key, current_bit, len(value)])
            current_bit += len(value)
            signals.append(value)
        
        signals.append(Signal(len(Cat(signals)) % 8)) # Round it up to length 8 * n

        self.debugger = debugger = UARTDebugger2(uart, int(len(Cat(signals)) / 8), self.depth, Cat(signals), data_domain, enable, timeout)
        self.data_format = data_format
        return debugger

    """Read data from the UARTDebugger2
    Parameters
    ----------
    callback : Function
        It is called with a dictionary of all signals values, it is called once for each sample.
    """
    def read(callback):
        port = serial.Serial(port=glob("/dev/serial/by-id/usb-FTDI_Lattice_ECP5_5G_VERSA_Board_*-if01-port0")[0], baudrate=1000000)
        port.write(b"\x00")

        while True:
            #while True:
            #    if port.read(1) == b'\n': break
            if port.read(1) == b'\n': break
        
        for x in range(self.depth):
            chars = port.read(5 * 2 + 1)
            word = int(chars, 16)