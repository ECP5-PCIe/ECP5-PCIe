from ecp5_pcie.crc import CRC, LCRC
from nmigen import *
from nmigen.sim import Simulator, Delay, Settle

def to_array(value : int, bits : int):
    result = []

    for i in range(bits):
        result.append(bool(value & (1 << i)))
    
    return result

def to_number(bits):
    result = 0

    for i in range(len(bits)):
        if bits[i]:
            result += 1 << i
    
    return result


# All input values are bool arrays
def reference_crc(polynomial, crc, bits):
    assert len(polynomial) == len(crc)
    for bit in bits:
        # See PCIe Base 1.1 Page 145
        current_input = bit ^ crc[-1]

        new_crc = crc.copy()

        assert polynomial[0] == True # Currently only this case is handled, maybe set the following to 0 or 1 otherwise
        new_crc[0] = current_input

        for i in range(1, len(crc)):
            if polynomial[i]:
                new_crc[i] = crc[i - 1] ^ current_input
            else:
                new_crc[i] = crc[i - 1]
        
        crc = new_crc
    
    return crc


def lcrc(data):
    bits = []
    for byte in data:
        bits += to_array(byte, 8)

    crc = reference_crc(to_array(0x04C11DB7, 32), to_array(0xFFFFFFFF, 32), bits)

    crc = [not value for value in crc]
    crc_old = crc.copy()

    crc[ 0: 8] = reversed(crc_old[ 0: 8])
    crc[ 8:16] = reversed(crc_old[ 8:16])
    crc[16:24] = reversed(crc_old[16:24])
    crc[24:32] = reversed(crc_old[24:32])

    return to_number(crc)




assert to_array(0x3E, 8) == [False, True, True, True, True, True, False, False]



if __name__ == "__main__":
    test_bytes = [0x1, 0x23] + [i for i in range(256)] * 4

    test_bytes = test_bytes

    m = Module()
    in_symbol = Signal(8)
    reset_crc = Signal(reset=1)
    m.submodules.crc = crc = LCRC(in_symbol, reset_crc)

    sim = Simulator(m)

    sim.add_clock(1, domain="sync")

    def process():
        for i in range(len(test_bytes) + 2):
            crc_value = ((yield crc.output))
            yield in_symbol.eq(test_bytes[min(i, len(test_bytes) - 1)])
            yield reset_crc.eq(0)
            print(i, hex(crc_value))
            yield

            if i == len(test_bytes) + 1:
                assert crc_value == lcrc(test_bytes)
                print("Test passed! LCRC:", hex(crc_value))

    sim.add_sync_process(process, domain="sync")

    sim.run()



    if True:
        m = Module()
        in_symbol = Signal(32)
        reset_crc = Signal(reset=1)
        m.submodules.crc = crc = LCRC(in_symbol, reset_crc)

        sim = Simulator(m)

        sim.add_clock(1, domain="sync")

        def process():
            for i in range(len(test_bytes) // 4 + 4):
                crc_value = ((yield crc.output))
                if i >= 2:
                    j = i - 2
                    yield in_symbol[ 0: 8].eq(test_bytes[min(4 * j + 0 + 2, len(test_bytes) - 1)])
                    yield in_symbol[ 8:16].eq(test_bytes[min(4 * j + 1 + 2, len(test_bytes) - 1)])
                    yield in_symbol[16:24].eq(test_bytes[min(4 * j + 2 + 2, len(test_bytes) - 1)])
                    yield in_symbol[24:32].eq(test_bytes[min(4 * j + 3 + 2, len(test_bytes) - 1)])
                else:
                    yield in_symbol[ 0: 8].eq(test_bytes[0])
                    yield in_symbol[ 8:16].eq(test_bytes[1])
                if i == 1:
                    yield reset_crc.eq(0)
                print(i, hex(crc_value))
                yield

                if i == len(test_bytes) // 4 + 3:
                    assert crc_value == lcrc(test_bytes)
                    print("Test passed! LCRC:", hex(crc_value))

        sim.add_sync_process(process, domain="sync")

        sim.run()