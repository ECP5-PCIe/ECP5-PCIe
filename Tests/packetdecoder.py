from ecp5_pcie.serdes import Ctrl, D
from ecp5_pcie.dllp import DLLPType

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

def match_all(symbols, symbol):
	value = True

	for s in symbols:
		value = value and s == symbol
	
	return value

def parse_data(symbols):
	result = []

	i = 0
	
	print("Parsing symbols")

	while i < len(symbols):
		if symbols[i] == Ctrl.COM:
			if match_all(symbols[i + 1 : i + 4], Ctrl.SKP):
				result.append([i, {"Type": "SKP"}])
				i = i + 4

			elif match_all(symbols[i + 1 : i + 4], Ctrl.FTS):
				result.append([i, {"Type": "FTS"}])
				i = i + 4

			elif match_all(symbols[i + 1 : i + 4], Ctrl.IDL):
				result.append([i, {"Type": "EIOS"}])
				i = i + 4

			elif match_all(symbols[i + 1 : i + 15], Ctrl.EIE) and symbols[i + 15] == D(10, 2):
				result.append([i, {"Type": "EIEOS"}])
				i = i + 16

			elif match_all(symbols[i + 10 : i + 14], D(10, 2)) or match_all(symbols[i + 10 : i + 14], D(5, 2)):
				result.append([i, {"Type": "TS", "data": {
					"Link": symbols[i + 1],
					"Lane": symbols[i + 2],
					"N_FTS": symbols[i + 3],
					"DRI": symbols[i + 4],
					"Ctrl": symbols[i + 5],
					"ID": symbols[i + 10] == D(10, 2),
				}}])
				i = i + 16
			
			else:
				i += 1
			
		elif symbols[i] == Ctrl.SDP and symbols[i + 7] == Ctrl.END:
			for s in symbols[i : i + 8]:
				print_symbol(s, end="\t")
			print()

			result.append([i, {"Type": "DLLP", "data": {
				"Type": DLLPType((symbols[i + 1] & 0xF0) >> 4),
				"Type2": symbols[i + 1] & 0x0F,
				"Data": symbols[i + 2 : i + 5],
				"CRC": symbols[i + 5 : i + 7],
				}}])

			i = i + 8
		
		elif symbols[i] == Ctrl.STP:
			end_index = i

			while symbols[end_index] != Ctrl.END and symbols[end_index] != Ctrl.EDB:
				end_index += 1
			
			dllp_data = symbols[i + 1 : end_index] # Without framing symbols
			tlp_data = symbols[i + 3 : end_index - 4] # Without DLLP stuff

			result.append([i, {"Type": "TLP", "data": {
				"Sequence Number": (dllp_data[0] << 8) + dllp_data[1],
				"Fmt"   :  (tlp_data[0] & 0xE0) >> 5,
				"Type"  :   tlp_data[0] & 0x1F,
				"TC"    :  (tlp_data[1] & 0x70) >> 4,
				"Attr"  :  (tlp_data[1] & 0x04) | ((tlp_data[2] & 0x30) >> 4),
				"TH"    :   tlp_data[1] & 0x01,
				"TD"    :  (tlp_data[2] & 0x80) >> 7,
				"EP"    :  (tlp_data[2] & 0x40) >> 6,
				"AT"    :  (tlp_data[2] & 0x0C) >> 2,
				"Length": ((tlp_data[2] & 0x03) << 8) | tlp_data[3],
				"Data"  :   tlp_data[4:]
				}}])
			
			i = end_index + 1
		
		else:
			i += 1
	


	print("Calculating symbol statistics")
	symbol_statistics = {}

	for symbol in symbols:
		if not symbol in symbol_statistics:
			symbol_statistics[symbol] = 0
		
		symbol_statistics[symbol] += 1
	


	return result, symbol_statistics