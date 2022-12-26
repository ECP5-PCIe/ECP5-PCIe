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

# Usage: python test_pcie_phy.py run
#        python test_pcie_phy.py grab
#
# Prints data received and how long it has been in L0

CAPTURE_DEPTH = 1024

# Disable debugging for speed optimization
NO_DEBUG = False

# Default mode is to record all received symbols
DEBUG_PACKETS = True

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
		uart = AsyncSerial(divisor = int(100), pins = uart_pins)
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
		elif DEBUG_PACKETS:
			# 64t 9R 9R 9T 9T 2v 4- 6D
			# t = Ticks since state was entered
			# R = RX symbol
			# T = TX symbol
			# v = RX valid
			# D = DTR Temperature, does not correspond to real temperature besides the range of 21-29 °C. After that in 10 °C steps (30 = 40 °C, 31 = 50 °C etc...), see TN1266

			rx_packet = Signal()
			tx_packet = Signal()

			rx_start_condition = (phy.ltssm.debug_state == State.L0) & ((lane.rx_symbol[0:9] == Ctrl.STP) | ((lane.rx_symbol[0:9] == Ctrl.SDP) & ((lane.rx_symbol[9:18] == 0) | (lane.rx_symbol[9:18] == 0b00010000))))
			tx_start_condition = (phy.ltssm.debug_state == State.L0) & ((lane.tx_symbol[0:9] == Ctrl.STP) | ((lane.tx_symbol[0:9] == Ctrl.SDP) & ((lane.tx_symbol[9:18] == 0) | (lane.tx_symbol[9:18] == 0b00010000))))
			
			with m.If(rx_start_condition):
				m.d.rx += rx_packet.eq(1)
			
			with m.If(tx_start_condition):
				m.d.rx += tx_packet.eq(1)
			
			with m.If((phy.ltssm.debug_state == State.L0) & (lane.rx_symbol[27:36] == Ctrl.END)):
				m.d.rx += rx_packet.eq(0)
			
			with m.If((phy.ltssm.debug_state == State.L0) & (lane.tx_symbol[27:36] == Ctrl.END)):
				m.d.rx += tx_packet.eq(0)
			

			rx_sample_data = Signal(range(CAPTURE_DEPTH))
			with m.If(rx_sample_data > 0):
				m.d.rx += rx_sample_data.eq(rx_sample_data - 1)
			
			with m.Elif(~rx_start_condition):
				m.d.rx += rx_packet.eq(0)

			with m.If(rx_start_condition):
				m.d.rx += rx_sample_data.eq(64)
			

			tx_sample_data = Signal(range(CAPTURE_DEPTH))
			with m.If(tx_sample_data > 0):
				m.d.rx += tx_sample_data.eq(tx_sample_data - 1)
			
			with m.Elif(~tx_start_condition):
				m.d.rx += tx_packet.eq(0)

			with m.If(tx_start_condition):
				m.d.rx += tx_sample_data.eq(64)


			time_since_state = Signal(64)
			
			with m.If(ltssm.debug_state != State.L0):
				m.d.rx += time_since_state.eq(0)
			with m.Else():
				m.d.rx += time_since_state.eq(time_since_state + 1)

			#with m.If(end_condition):
			#	m.d.rx += sample_data.eq(0)
			

			rx_time = Signal(64)

			#m.d.rx += rx_time.eq(rx_time + 1)
			m.d.rx += rx_time.eq(Cat(phy.dll_tlp_rx.buffer.slots_occupied, phy.dll.scheduled_ack, phy.dll.schedule_ack_nak, phy.dll_tlp_rx.nak_scheduled, phy.dll_tlp_rx.buffer.slots_full, Signal(1),
				phy.dll_tlp_rx.debug, phy.tlp.debug, phy.dll_tlp_tx.debug, phy.dll_tlp_tx.debug_crc_output))

			#m.d.rx += rx_time.eq(Cat(phy.dll_tlp_tx.debug[4], phy.dll_tlp_tx.debug[4], phy.dll_tlp_tx.debug[4], phy.dll_tlp_tx.debug[4], phy.dll_tlp_tx.debug_crc_input[4:], phy.dll_tlp_tx.debug_crc_output))

			drxtime = Signal(64 * 4)
			m.d.rx += drxtime.eq(Cat(drxtime[64 : 64 * 4], rx_time))


			#delayed_rx_symbol = Signal(len(lane.rx_symbol) * 3)
			#delayed_tx_symbol = Signal(len(lane.tx_symbol) * 3)
#
			#m.d.rx += delayed_rx_symbol.eq(Cat(delayed_rx_symbol[36 : 36 * 3], lane.rx_symbol))
			#m.d.rx += delayed_tx_symbol.eq(Cat(delayed_tx_symbol[36 : 36 * 3], lane.tx_symbol))


			m.submodules += UARTDebugger3(uart, 19 + 8, CAPTURE_DEPTH, Cat(
				time_since_state,
				lane.rx_symbol[:36], lane.tx_symbol[:36],# lane.tx_symbol,
				#*[Cat(phy.dll_tlp_rx.debug2.word_select(i, 8), 0) for i in range(4)], *[Cat(phy.dll_tlp_rx.debug3.word_select(i, 8), 0) for i in range(4)],
				lane.rx_aligned, lane.rx_locked & lane.rx_present & lane.rx_aligned, dtr.temperature, phy.ltssm.debug_state, drxtime[:64]#, phy.dll.tx.started_sending, phy.dll.tx.started_sending#dtr.temperature
				), "rx", enable = rx_packet | tx_packet | rx_start_condition | tx_start_condition)#, enable = phy.ltssm.debug_state == State.L0)
		else:
			# 64t 9R 9R 9T 9T 2v 4- 6D
			# t = Ticks since state was entered
			# R = RX symbol
			# T = TX symbol
			# v = RX valid
			# D = DTR Temperature, does not correspond to real temperature besides the range of 21-29 °C. After that in 10 °C steps (30 = 40 °C, 31 = 50 °C etc...), see TN1266

			start_condition = (phy.ltssm.debug_state == State.L0) & (lane.rx_symbol[0:9] == Ctrl.STP)# & ~(lane.rx_symbol[27:36] == 0x74)# & ((lane.rx_symbol[27:36][5] == 0b00100) | (lane.rx_symbol[27:36][5] == 0b00101))# (lane.rx_symbol [0:9] == Ctrl.STP)
			#start_condition = (phy.ltssm.debug_state == State.L0) & ((lane.tx_symbol[0:9] == Ctrl.STP) | (phy.dll_tlp_tx.debug[0:4] != 0))# & ~(lane.rx_symbol[27:36] == 0x74)# & ((lane.rx_symbol[27:36][5] == 0b00100) | (lane.rx_symbol[27:36][5] == 0b00101))# (lane.rx_symbol [0:9] == Ctrl.STP)
			#start_condition = (phy.ltssm.debug_state == State.L0) & (lane.rx_symbol[0:9] == Ctrl.STP) & ((lane.rx_symbol[27:36][0:5] == 0b00100) | (lane.rx_symbol[27:36][0:5] == 0b00101))# (lane.rx_symbol [0:9] == Ctrl.STP)
			#start_condition = ((phy.ltssm.debug_state == State.L0) & (lane.tx_symbol[0:9] == Ctrl.STP)) | start_condition
			#start_condition = ((phy.ltssm.debug_state == State.L0) & (lane.rx_symbol[0:9] == Ctrl.SDP) & ((lane.rx_symbol[9:18] == 0b0) | (lane.rx_symbol[9:18] == 0b10000))) | start_condition
			#start_condition = ((phy.ltssm.debug_state == State.L0) & (lane.tx_symbol[0:9] == Ctrl.SDP) & ((lane.tx_symbol[9:18] == 0b0) | (lane.tx_symbol[9:18] == 0b10000))) | start_condition
			end_condition = lane.rx_symbol[27:36] == Ctrl.END
			end_condition = (lane.tx_symbol[27:36] == Ctrl.END) | end_condition

			time_since_state = Signal(64)
			
			if True:
				with m.If(ltssm.debug_state != State.L0):
					m.d.rx += time_since_state.eq(0)
				with m.Else():
					m.d.rx += time_since_state.eq(time_since_state + 1)
					#with m.If(has_symbol(lane.rx_symbol, Ctrl.STP) & (phy.ltssm.debug_state == State.L0)):
					#    m.d.rx += time_since_state.eq(time_since_state + 1)
			
			else:
				#m.d.rx += time_since_state.eq(time_since_state + 1)
				#m.d.rx += time_since_state.eq(phy.dll.status.receive_buffer_occupation)
				m.d.rx += time_since_state.eq(ecp5_phy.phy.dll_tlp_tx.debug_crc_output)
			
			#sample_data = Signal()
			#sample_data2 = Signal()
			#sample_data3 = Signal()
			#with m.If(start_condition):
			#	m.d.rx += sample_data.eq(1)
			#
			#with m.Elif(end_condition):
			#	m.d.rx += sample_data.eq(0)
			#
			#m.d.rx += sample_data2.eq(sample_data)
			#m.d.rx += sample_data3.eq(sample_data2)

			sample_data = Signal(range(CAPTURE_DEPTH))
			with m.If(sample_data > 0):
				m.d.rx += sample_data.eq(sample_data - 1)

			with m.If(start_condition):
				m.d.rx += sample_data.eq(64)

			#with m.If(end_condition):
			#	m.d.rx += sample_data.eq(0)
			

			rx_time = Signal(64)

			#m.d.rx += rx_time.eq(rx_time + 1)
			m.d.rx += rx_time.eq(Cat(phy.dll_tlp_rx.buffer.slots_occupied, phy.dll.scheduled_ack, phy.dll.schedule_ack_nak, phy.dll_tlp_rx.nak_scheduled, phy.dll_tlp_rx.buffer.slots_full, Signal(1),
				phy.dll_tlp_rx.debug, phy.tlp.debug, phy.dll_tlp_tx.debug, phy.dll_tlp_tx.debug_crc_output))

			#m.d.rx += rx_time.eq(Cat(phy.dll_tlp_tx.debug[4], phy.dll_tlp_tx.debug[4], phy.dll_tlp_tx.debug[4], phy.dll_tlp_tx.debug[4], phy.dll_tlp_tx.debug_crc_input[4:], phy.dll_tlp_tx.debug_crc_output))

			drxtime = Signal(64 * 4)
			m.d.rx += drxtime.eq(Cat(drxtime[64 : 64 * 4], rx_time))


			delayed_rx_symbol = Signal(len(lane.rx_symbol) * 3)
			delayed_tx_symbol = Signal(len(lane.tx_symbol) * 3)

			m.d.rx += delayed_rx_symbol.eq(Cat(delayed_rx_symbol[36 : 36 * 3], lane.rx_symbol))
			m.d.rx += delayed_tx_symbol.eq(Cat(delayed_tx_symbol[36 : 36 * 3], lane.tx_symbol))


			m.submodules += UARTDebugger3(uart, 19 + 8, CAPTURE_DEPTH, Cat(
				time_since_state,
				delayed_rx_symbol[:36], delayed_tx_symbol[:36],# lane.tx_symbol,
				#*[Cat(phy.dll_tlp_rx.debug2.word_select(i, 8), 0) for i in range(4)], *[Cat(phy.dll_tlp_rx.debug3.word_select(i, 8), 0) for i in range(4)],
				lane.rx_aligned, lane.rx_locked & lane.rx_present & lane.rx_aligned, dtr.temperature, phy.ltssm.debug_state, drxtime[:64]#, phy.dll.tx.started_sending, phy.dll.tx.started_sending#dtr.temperature
				), "rx", enable = (sample_data > 0) | start_condition)#, enable = phy.ltssm.debug_state == State.L0)

		return m

# -------------------------------------------------------------------------------------------------

import sys
import serial
from glob import glob

import os
#os.environ["AMARANTH_verbose"] = "Yes"


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
			port = serial.Serial(port=glob("/dev/serial/by-id/usb-FTDI_Lattice_ECP5_5G_VERSA_Board_*-if01-port0")[0], baudrate=1000000)
			port.write(b"\x00")
			indent = 0
			last_time = 0
			last_realtime = 0

			while True:
				#while True:
				#    if port.read(1) == b'\n': break
				if port.read(1) == b'\n': break

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


			# The data is read into a byte array (called word) and then the relevant bits are and'ed out and right shifted.
			a_1 = None
			b_1 = None
			for x in range(CAPTURE_DEPTH):
				# 64t 9R 9R 9T 9T 2v 2-
				# t = Ticks since state was entered
				# R = RX symbol
				# T = TX symbol
				# v = RX valid
				chars = port.read((19 + 8) * 2 + 1)
				try:
					data = int(chars, 16)
				except:
					print("err " + str(chars))
					data = 0
				time = get_bytes(data, 0, 8)
				symbols = [get_bits(data, 64 + 9 * i, 9) for i in range(8)]
				valid = [get_bits(data, 64 + 9 * 8, 1), get_bits(data, 65 + 9 * 8, 1)]
				ltssm = get_bits(data, 18 * 8, 8)
				real_time = get_bits(data, 19 * 8, 64)

				if a_1 == None:
					a_1 = time
					b_1 = real_time # 100 MHz

				print("{:{width}}".format("{:,}".format(time), width=15), end=" \t")
				#print("{:{width}}".format("{:,}".format(real_time), width=15), end=" \t")
				print("{:{width}}".format("{}".format(hex(real_time)), width=15), end=" \t")
				for i in range(len(symbols)):
					#if i < 2:
					#    print_symbol(symbols[i], 0, end="V\t" if valid[i] else "E\t")
					#else:
					print_symbol(symbols[i], end="\t")
					if i == 3:
						print(valid[0], end="\t")

				print(end="\t")
				print(ltssm, end=" \t")
				print(DTR.CONVERSION_TABLE[get_bits(data, 17 * 8 + 2, 6)], end=" °C\n")
			
			#print((time - a_1) / (real_time - b_1) * 100, "MHz")
