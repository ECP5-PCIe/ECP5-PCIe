from amaranth import *
from amaranth.build import *
from amaranth.lib.cdc import FFSynchronizer
from amaranth_boards import versa_ecp5_5g as FPGA
from amaranth_stdio.serial import AsyncSerial
from ecp5_pcie.utils.utils import UARTDebugger3
from ecp5_pcie.ecp5_phy_x1 import LatticeECP5PCIePhy   
from ecp5_pcie.utils.parts import DTR
from ecp5_pcie.ltssm import State
from ecp5_pcie.serdes import Ctrl
from ecp5_pcie.dll import State as DLState
import packetdecoder

# Usage: python test_pcie_phy.py run
#        python test_pcie_phy.py grab
#
# Prints data received and how long it has been in L0

CAPTURE_DEPTH = 2048

# Disable debugging for speed optimization
NO_DEBUG = False

# Default mode is to record all received symbols
DEBUG_PACKETS = False

DEBUG_CHANGED = True

class SERDESTestbench(Elaboratable):
	def elaborate(self, platform):
		m = Module()

		m.submodules.phy = ecp5_phy = LatticeECP5PCIePhy(support_5GTps=False)
		phy = ecp5_phy.phy

		ltssm = phy.ltssm
		lane = phy.descrambled_lane
		#lane = ecp5_phy.aligner

		# Temperature sensor, the chip gets kinda hot
		refclkcounter = Signal(32)
		m.d.sync += refclkcounter.eq(refclkcounter + 1)

		sample = Signal()
		m.d.sync += sample.eq(refclkcounter[25])
		m.submodules.dtr = dtr = DTR(start=refclkcounter[25] & ~sample)

		leds_alnum = Cat(platform.request("alnum_led", 0))
		leds = Cat(platform.request("led", i) for i in range(8))

		m.d.comb += leds_alnum.eq(ltssm.debug_state)
		m.d.comb += leds.eq(ltssm.debug_state)

		uart_pins = platform.request("uart", 0)
		uart = AsyncSerial(divisor = int(20), pins = uart_pins)
		m.submodules += uart
		
		platform.add_resources([Resource("test", 0, Pins("B19", dir="o"))])
		#m.d.comb += platform.request("test", 0).o.eq(ClockSignal("rx"))
		m.d.comb += platform.request("test", 0).o.eq(ecp5_phy.serdes.rx_clk)
		platform.add_resources([Resource("test", 1, Pins("A18", dir="o"))])
		m.d.comb += platform.request("test", 1).o.eq(ClockSignal("rxf"))

		def has_symbol(symbols, symbol):
			assert len(symbols) % 9 == 0

			has = 0

			for i in range(int(len(symbols) / 9)):
				has |= symbols[i * 9 : i * 9 + 9] == symbol
			
			return has


		if NO_DEBUG:
			pass
		elif DEBUG_CHANGED:
			# 64t 9R 9R 9T 9T 2v 4- 6D
			# t = Ticks since state was entered
			# R = RX symbol
			# T = TX symbol
			# v = RX valid
			# D = DTR Temperature, does not correspond to real temperature besides the range of 21-29 °C. After that in 10 °C steps (30 = 40 °C, 31 = 50 °C etc...), see TN1266

			time_since_state = Signal(64)
			
			with m.If(ltssm.debug_state != State.L0):
				m.d.rx += time_since_state.eq(0)
			with m.Else():
				m.d.rx += time_since_state.eq(time_since_state + 1)

			#with m.If(end_condition):
			#	m.d.rx += sample_data.eq(0)
			

			rx_time = Signal(48)

			m.d.rx += rx_time.eq(rx_time + 1)
			
			symbol = Cat(lane.rx_symbol[:36], lane.tx_symbol[:36])


			last_symbol = Signal(len(symbol))

			m.d.rx += last_symbol.eq(symbol)


			m.submodules += UARTDebugger3(uart, 6 + 9, CAPTURE_DEPTH, Cat(rx_time, symbol), "rx", enable = (symbol != last_symbol) & (ltssm.debug_state == State.L0) & (phy.dll.debug_state == DLState.DL_Active))#, enable = phy.ltssm.debug_state == State.L0)

		return m

# -------------------------------------------------------------------------------------------------

import sys
import serial
from glob import glob

import os
#os.environ["AMARANTH_verbose"] = "Yes"

# Prints a symbol as K and D codes
def print_symbol(symbol, end=""):
	xa = symbol & 0b11111
	ya = (symbol & 0b11100000) >> 5

	if symbol & 0x1ff == 0x1ee:
		print("Error\t", end=end)

	# Convert symbol data to a string which represents it
	elif symbol & 0x100 == 0x100:
		if xa == 27 and ya == 7:
			print("STP\t", end=end)
		elif xa == 23 and ya == 7:
			print("PAD\t", end=end)
		elif xa == 29 and ya == 7:
			print("END\t", end=end)
		elif xa == 30 and ya == 7:
			print("EDB\t", end=end)
		elif xa == 28:
			if ya == 0:
				print("SKP\t", end=end)
			if ya == 1:
				print("FTS\t", end=end)
			if ya == 2:
				print("SDP\t", end=end)
			if ya == 3:
				print("IDL\t", end=end)
			if ya == 5:
				print("COM\t", end=end)
			if ya == 7:
				print("EIE\t", end=end)
		else:
			print("{}{}{}.{} \t{}".format(
				"L" if symbol & (1 << 9) else " ",
				"K" if symbol & (1 << 8) else "D",
				xa, ya, hex(symbol & 0xFF).split("x")[1]
			), end=end)
	else:
		print("{}{}{}.{} \t{}".format(
			"L" if symbol & (1 << 9) else " ",
			"K" if symbol & (1 << 8) else "D",
			xa, ya, hex(symbol & 0xFF).split("x")[1]
		), end=end)

# Returns selected bit range from a byte array
def get_bits(word, offset, count):
	return (word & ((2 ** count - 1) << offset)) >> offset

# Returns selected byte range from a byte array
def get_bytes(word, offset, count):
	return (word & ((2 ** (count * 8) - 1) << (offset * 8))) >> (offset * 8)

entry_length = (6 + 9) * 2 + 1

if __name__ == "__main__":
	for arg in sys.argv[1:]:
		if arg == "speed":
			plat = FPGA.VersaECP55GPlatform(toolchain="Trellis")
			plat.device = "LFE5UM-25F"
			plat.speed = 6
			plat.build(SERDESTestbench(), do_program=False)

		if arg == "run":
			print("Building...")

			FPGA.VersaECP55GPlatform().build(SERDESTestbench(), do_program=True, nextpnr_opts="-r")

			with open("build/top.tim") as logfile:
				log = logfile.readlines()

				utilisation = []
				log_utilisation = False

				clock_speed = {}

				for line in log:
					if log_utilisation and line != "\n":
						utilisation.append(line)

					if line == "Info: Device utilisation:\n":
						log_utilisation = True
					
					if log_utilisation and line == "\n":
						log_utilisation = False

					if line.startswith("Info: Max frequency for clock"):
						values = line[:-1].split(":")

						clock_speed[values[1]] = values[2]
				
				for line in utilisation:
					print(line[:-1])
				
				print()

				for domain in clock_speed:
					print(f"{domain}:{clock_speed[domain]}")


		if arg == "grab":
			#port = serial.Serial(port=glob("/dev/serial/by-id/usb-FTDI_Lattice_ECP5_5G_VERSA_Board_*-if01-port0")[0], baudrate=1000000)
			port = serial.Serial(port=glob("/dev/serial/by-id/usb-FTDI_Lattice_ECP5_5G_VERSA_Board_*-if01-port0")[0], baudrate=5000000)
			port.write(b"\x00")
			indent = 0
			last_time = 0
			last_realtime = 0

			while True:
				#while True:
				#    if port.read(1) == b'\n': break
				if port.read(1) == b'\n': break

			# The data is read into a byte array (called word) and then the relevant bits are and'ed out and right shifted.
			a_1 = None
			b_1 = None

			for x in range(CAPTURE_DEPTH):
				# 64t 9R 9R 9T 9T 2v 2-
				# t = Ticks since state was entered
				# R = RX symbol
				# T = TX symbol
				# v = RX valid
				chars = port.read(entry_length)

				try:
					data = int(chars, 16)
				except:
					print("err " + str(chars))
					data = 0
				time = get_bytes(data, 0, 6)
				symbols = [get_bits(data, 48 + 9 * i, 9) for i in range(8)]

				print("{:{width}}".format("{:,}".format(time), width=15), end=" \t")
				for i in range(len(symbols)):
					#if i < 2:
					#    print_symbol(symbols[i], 0, end="V\t" if valid[i] else "E\t")
					#else:
					print_symbol(symbols[i], end="\t")
					if i == 3:
						print(end="\t")

				print()
			
			#print((time - a_1) / (real_time - b_1) * 100, "MHz")

		if arg == "record":
			#port = serial.Serial(port=glob("/dev/serial/by-id/usb-FTDI_Lattice_ECP5_5G_VERSA_Board_*-if01-port0")[0], baudrate=1000000)
			port = serial.Serial(port=glob("/dev/serial/by-id/usb-FTDI_Lattice_ECP5_5G_VERSA_Board_*-if01-port0")[0], baudrate=5000000, timeout=0.01)

			with open("tlprecord.bin", "ab") as file:
				while True:
					port.write(b"\x00")
					indent = 0
					last_time = 0
					last_realtime = 0

					while True:
						#while True:
						#    if port.read(1) == b'\n': break
						if port.read(1) == b'\n': break
					
					i = 0

					for x in range(CAPTURE_DEPTH):
						# 64t 9R 9R 9T 9T 2v 2-
						# t = Ticks since state was entered
						# R = RX symbol
						# T = TX symbol
						# v = RX valid
						chars = port.read(entry_length)
						#print(chars)

						if len(chars) == entry_length:
							file.write(chars)
						
						else:
							break
					
					print(x)

		if arg == "analyze":
			with open("tlprecord.bin", "rb") as file:
				chars = file.read()
				index = 0

				rx_symbols = []
				tx_symbols = []

				while index < len(chars):
					line = chars[index : index + entry_length]
					index += entry_length

					try:
						data = int(line, 16)

					except:
						print("err " + str(line))
						data = 0

					time = get_bytes(data, 0, 6)
					symbols = [get_bits(data, 48 + 9 * i, 9) for i in range(8)]
					rx_symbols += symbols[0 : 4]
					tx_symbols += symbols[4 : 8]

					#print("{:{width}}".format("{:,}".format(time), width=15), end=" \t")
					#for i in range(len(symbols)):
					#	#if i < 2:
					#	#    print_symbol(symbols[i], 0, end="V\t" if valid[i] else "E\t")
					#	#else:
					#	print_symbol(symbols[i], end="\t")
					#	if i == 3:
					#		print(end="\t")
#
					#print()
				
				decoded, symbol_statistics = packetdecoder.parse_data(rx_symbols)
				cnts = {}
				for index, packet in decoded:
					print(index, packet["Type"])
					t = packet["Type"]
					if not t in cnts:
						cnts[t] = 0

					cnts[t] += 1
				
				print()
				print(cnts)
				print()
				for key in symbol_statistics:
					if not key & 0x100:
						print_symbol(key)
						print(f": {symbol_statistics[key]}")
						
				for key in symbol_statistics:
					if key & 0x100:
						print_symbol(key)
						print(f": {symbol_statistics[key]}")