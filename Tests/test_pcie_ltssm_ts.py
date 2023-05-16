from amaranth import *
from amaranth.build import *
from amaranth.lib.cdc import FFSynchronizer
from amaranth_boards import versa_ecp5_5g as FPGA
from amaranth_stdio.serial import AsyncSerial
from ecp5_pcie.utils.utils import UARTDebugger3
from ecp5_pcie.ecp5_phy_x1 import LatticeECP5PCIePhy   
from ecp5_pcie.utils.parts import DTR
from ecp5_pcie.ltssm import State
from ecp5_pcie.dll import State as DLLState
from ecp5_pcie.serdes import Ctrl
import json, math

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

		#print(ecp5_phy.state_list)
		
		#print(len(ecp5_phy.state_list))
		x = 0
		state_sig = []
		decode_list = []
		for s_name in ecp5_phy.state_list:
			sig = ecp5_phy.state_list[s_name]
			x += len(sig)
			#print(s_name, sig)
			decode_list.append([len(sig), s_name])
			state_sig.append(sig)

		with open("test_pcie_ltssm_ts.json", "w") as file:
			json.dump(decode_list, file)

		state_sig = Cat(state_sig)
		#print(x)
		#print(state_sig)
		#lc = 0
		#for l in decode_list:
		#	lc += l[0]
		#	print(l)
		#print(len(state_sig), lc)
		#exit()

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

		rx_time = Signal(64)
		m.d.rx += rx_time.eq(rx_time + 1)

		# debug_states = Cat(ltssm.debug_state, phy.dll.debug_state, phy.dll_tlp_rx.debug_state, phy.dll_tlp_tx.debug_state, phy.tlp.debug_state)
		debug_states = Cat(phy.rx.ts, phy.tx.ts, ltssm.debug_state, phy.dll.debug_state, phy.dll_tlp_rx.debug_state, phy.dll_tlp_tx.debug_state, phy.tlp.debug_state)
		
		last_state = Signal(len(debug_states))
		m.d.rx += last_state.eq(debug_states)

		delayed_sig = Signal(len(state_sig))
		m.d.rx += delayed_sig.eq(state_sig)

		padding = Signal(((len(state_sig) + 7) // 8) * 8 - len(state_sig))

		enable = Signal()
		ecnt = Signal(3)
		with m.If(ltssm.debug_state > State.Polling_Active_TS):
			m.d.rx += enable.eq(1)
			m.d.rx += ecnt.eq(7)
		
		with m.Else():
			with m.If((ecnt > 0) & (last_state != debug_states)):
				m.d.rx += ecnt.eq(ecnt - 1)
			
			with m.Else():
				m.d.rx += enable.eq(0)
		
		#with m.If(ltssm.debug_state == State.Detect):
		#	m.d.rx += ecnt.eq(7)

		m.d.rx += enable.eq(1)
		


		at_start = False # Capture state after transition, if true time is at start of state, otherwise at end of state
		m.submodules += UARTDebugger3(uart, (len(state_sig) + 7) // 8 + 8, CAPTURE_DEPTH, Cat(rx_time, state_sig if at_start else delayed_sig, padding), "rx",
			enable = (last_state != debug_states) & enable & (last_state != 0))

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
			port = serial.Serial(port=glob("/dev/serial/by-id/usb-FTDI_Lattice_ECP5_5G_VERSA_Board_*-if01-port0")[0], baudrate=1000000, timeout=0.1)
			port.write(b"\x00")
			indent = 0
			last_time = 0
			last_realtime = 0

			with open("test_pcie_tlp_state.json", "r") as file:
				data_format = json.load(file)
			
			data_length = 0
			for line in data_format:
				data_length += line[0]

			while True:
				#while True:
				#    if port.read(1) == b'\n': break
				if port.read(1) == b'\n': break

			# Returns selected bit range from a byte array
			def get_bits(word, offset, count):
				return (word & ((2 ** count - 1) << offset)) >> offset

			# Returns selected byte range from a byte array
			def get_bytes(word, offset, count):
				return (word & ((2 ** (count * 8) - 1) << (offset * 8))) >> (offset * 8)


			# The data is read into a byte array (called word) and then the relevant bits are and'ed out and right shifted.
			a_1 = None
			b_1 = None
			with open("ResultTS.csv", "a") as rfile:
				#json.dump({"Format": data_format}, rfile)
				data_format = [[64, "Time"], *data_format]
				rfile.write(f'Format, {", ".join([f"{part[1]}: {part[0]}" for part in data_format])}\n')
				for x in range(CAPTURE_DEPTH):
					# 64t 9R 9R 9T 9T 2v 2-
					# t = Ticks since state was entered
					# R = RX symbol
					# T = TX symbol
					# v = RX valid
					chars = port.read((8 + (data_length + 7) // 8) * 2 + 1)
					if len(chars) < (8 + (data_length + 7) // 8) * 2 + 1:
						break

					try:
						data = int(chars, 16)

					except:
						print("err " + str(chars))
						data = 0
						exit()

					time = get_bytes(data, 0, 8)
					data_list = []
					offset = 0
					for line in data_format:
						data_list.append(get_bits(data, offset, line[0]))
						offset += line[0]
					
					#rfile.write(f'{{"Data": [{", ".join([f"{data_list[i]:{math.ceil(math.log10(2) * data_format[i][0])}}" for i in range(len(data_list))])}]}}\n')
					rfile.write(f'Data, {", ".join([f"{data_list[i]:{math.ceil(math.log10(2) * data_format[i][0])}}" for i in range(len(data_list))])}\n')
					print(x)
				
			
			#print((time - a_1) / (real_time - b_1) * 100, "MHz")

		if arg == "analyze":
			with open("ResultTS.csv", "r") as rfile:
				lines = rfile.readlines()
				data_index = []
				data = {}
				data_count = 0

				for line in lines:
					parts = line.split(",")
					
					if parts[0].strip() == "Format":
						data_index = []

						for part in parts[1:]:
							name, n_bits = part.split(":")
							data_index.append([name.strip(), int(n_bits)])

							if not name.strip() in data:
								data[name.strip()] = []
					
					elif parts[0].strip() == "Data":
						data_count += 1
						i = 0

						for part in parts[1:]:
							data[data_index[i][0]].append(int(part))
							i += 1
			
			for x in data_index:
				print(*x)

			def get_element(i, cond):
				for j in range(len(data_index)):
					if cond(data_index[j][0]):
						return data[data_index[j][0]][i]

			def get_signal(i, name):
				result = {}
				for j in range(len(data_index)):
					if data_index[j][0].startswith(name):
						result[data_index[j][0][len(name) + 1:]] = data[data_index[j][0]][i]
					
				return result

			def get_signal_raw(i, name):
				result = 0
				n = 0
				for j in range(len(data_index)):
					if data_index[j][0].startswith(name):
						result |= data[data_index[j][0]][i] << n
						n += data_index[j][0]
					
				return result
			
			# Validate
			chain = 0
			for a in range(data_count):
				f = lambda x : get_element(a, lambda s: s.endswith(x))
				ltssm_state = f("debug_state")
				#print(ltssm_state)
				#if f("RX.consecutive"):
				#	print(f("RX.consecutive"), f("RX.ts.ctrl.disable_link"), f("RX.ts.ctrl.loopback"), f("RX.ts.ctrl.hot_reset"), f("RX.ts.ctrl.disable_scrambling"), f("RX.ts.ctrl.compliance_receive"))
				chain += 1
				if True:#ltssm_state == State.Detect:

				#for i in range(1, data_count - 1):
					if True:#chain >= State.Detect_Active:
						#print()
						#for i in range(a - chain, a):
						if True:
							i = a
							#print(i)
							f = lambda x, o = 0 : get_element(i + o, lambda s: s.endswith(x))
							def print_state(name, smap):
								state = f(name)
								state_next = f(name, +1)
								time_in_state = time - data["Time"][i - 1]
								sname = name.split(".")[-2]

								if state != state_next:
									#print(f("err_cnt_1", 1) - f("err_cnt_1"), f("err_cnt_2", 1) - f("err_cnt_2"))
									if type(smap) is list:
										print(f"{time:16}\t{time_in_state:8}\t{sname}: {smap[state]} -> {smap[state_next]}")

									else:
										print(f"{time:16}\t{time_in_state:8}\t{sname}: {smap(state).name} -> {smap(state_next).name}")
							
							def print_if_diff(name):
								before = get_signal(i, name)
								after = get_signal(i + 1, name)
								if before != after:
									print(f"{name}: ", end = "")
									for kn in after:
										kn2 = ".".join([p[0] + p[-1] for p in kn.split(".")])
										print(f"{kn2}: {after[kn]}, ", end = "")
									
									print()
									#print(name, after)

							ltssm_state_last = f("LTSSM.debug_state", -1)
							ltssm_state = f("LTSSM.debug_state")
							ltssm_state_next = f("LTSSM.debug_state", +1)
							dll_state_last = f("DLL.debug_state", -1)
							dll_state = f("DLL.debug_state")
							dll_state_next = f("DLL.debug_state", +1)
							time = f("Time")
							time_in_state = time - data["Time"][i - 1]
							#if ltssm_state == State.Configuration:
							#	print(f"{time_in_state:8}\t{State(ltssm_state).name} -> {State(ltssm_state_next).name}")
							#	#print(time, time_in_state / 62500, State(ltssm_state).name)
							#	#print(f("RX.ts.link.number"), f("TX.ts.link.number"), f("RX.ts.link.valid"), f("RX.ts.ts_id"), f("RX.ts.rate.speed_change"))
							#	print(f("RX.consecutive"), f("RX.ts.valid"), f("RX.ts.ts_id"), f("RX.ts.link.valid"), f("RX.ts.lane.valid"))

							print_state("LTSSM.debug_state", State)
							print_state("DLL.debug_state", DLLState)
							print_state("TLPReceiver.debug_state", [i for i in range(256)])
							print_state("TLPTransmitter.debug_state", [i for i in range(16)])
							print_state("TLP.debug_state", [i for i in range(16)])
							print_if_diff("LatticeECP5PCIePhy.PCIePhy.PCIePhyTX.ts")
							print_if_diff("LatticeECP5PCIePhy.PCIePhy.PCIePhyRX.ts")
							if f("TLP.debug_header") != f("TLP.debug_header", -1):
								print(hex(f("TLP.debug_header")))


							for j in range(len(data_index)):
								if data_index[j][0].startswith(name):
									if data[data_index[j][0]][i] != data[data_index[j][0]][i + 1]:
										print(data_index[j][0], data[data_index[j][0]][i + 1])
							
							#if ltssm_state != ltssm_state_next:
							#	print(f"{time_in_state:8}\tLTSSM: {State(ltssm_state).name} -> {State(ltssm_state_next).name}")
#
							#if dll_state != dll_state_next:
							#	print(f"{time_in_state:8}\t  DLL: {DLLState(dll_state).name} -> {DLLState(dll_state_next).name}")
							
							#print(f("TLPReceiver.debug_state"), f("TLPTransmitter.debug_state"), f("TLP.debug_state"))

							#if ltssm_state == State.Configuration_Linkwidth_Accept:
							#	print(f"{time_in_state:8}\t{State(ltssm_state).name} -> {State(ltssm_state_next).name}")
							#	#print(time, time_in_state / 62500, State(ltssm_state).name)
							#	#print(f("RX.ts.link.number"), f("TX.ts.link.number"), f("RX.ts.link.valid"), f("RX.ts.ts_id"), f("RX.ts.rate.speed_change"))
							#	print("\t", f("RX.ts.link.valid"), f("RX.ts.lane.valid"), f("RX.ts.link.number"), f("RX.ts.lane.number"))
							#	print("\t", f("TX.ts.link.valid"), f("TX.ts.lane.valid"), f("TX.ts.link.number"), f("TX.ts.lane.number"))
							
							if ltssm_state == State.Detect:
								#print(f("LatticeECP5PCIePhy.PCIePhy.PCIePhyTX.ts.link.number") )
								assert f(".link.up") == 0
							
							if ltssm_state == State.Polling:
								#print(f("LatticeECP5PCIePhy.PCIePhy.PCIePhyTX.ts.link.number") )
								assert f("LatticeECP5PCIePhy.PCIePhy.PCIePhyTX.ts.link.valid") == 0
								assert f("LatticeECP5PCIePhy.PCIePhy.PCIePhyTX.ts.lane.valid") == 0
								assert f("LatticeECP5PCIePhy.PCIePhy.PCIePhyTX.ts.ts_id") == 0
							
							if ltssm_state == State.Polling_Configuration:
								assert f("LatticeECP5PCIePhy.PCIePhy.PCIePhyTX.ts.link.valid") == 0
								assert f("LatticeECP5PCIePhy.PCIePhy.PCIePhyTX.ts.lane.valid") == 0
								assert f("LatticeECP5PCIePhy.PCIePhy.PCIePhyTX.ts.ts_id") == 1
							
							if ltssm_state == State.Configuration_Linkwidth_Start:
								#assert f("LatticeECP5PCIePhy.PCIePhy.PCIePhyTX.ts.link.valid") == 0
								#print(f("RX.ts.link.number"), f("TX.ts.link.number"), f("RX.ts.link.valid"), f("RX.ts.ts_id"), f("RX.inverted"))
								#print(f("RX.ts.rate.gen1"), f("RX.ts.rate.gen2"), f("RX.ts.rate.reserved1"))
								#print(f("TX.ts.rate.gen1"), f("TX.ts.rate.gen2"), f("TX.ts.rate.reserved1"))
								assert f("LatticeECP5PCIePhy.PCIePhy.PCIePhyTX.ts.lane.valid") == 0
								assert f("LatticeECP5PCIePhy.PCIePhy.PCIePhyTX.ts.ts_id") == 0
							
							if State.Polling <= ltssm_state <= State.Configuration:#State.Configuration <= ltssm_state <= State.Configuration_Idle or ltssm_state == State.Polling_Active_TS:
								print("\t\t", f("err_cnt_1"), f("err_cnt_2"), f("RX.ts.link.number"), f("TX.ts.link.number"), f("RX.ts.link.valid"), f("RX.ts.lane.valid"), f("RX.ts.ts_id"), f("RX.consecutive"), f("RX.ts.ctrl.compliance_receive"), f("RX.ts.ctrl.loopback"), f("status.retry_buffer_occupation"),
									f("RX.ts.rate.gen1"), f("RX.ts.rate.gen2"), f("TX.ts.rate.gen1"), f("TX.ts.rate.gen2"))

					chain = 0
			
			exit()

			for i in range(data_count - 1):
				print(f'{get_element(i, lambda s: s.endswith("debug_state"))} -> {get_element(i + 1, lambda s: s.endswith("debug_state"))}')
				for parameter, _ in data_index:
					if data[parameter][i] != data[parameter][i + 1]:
						print(f"{parameter}: {data[parameter][i]} -> {data[parameter][i + 1]}")
				
				print()

			#for i in range(data_count):
			#	ltssm_state = get_element(i, lambda s: s.endswith("debug_state"))