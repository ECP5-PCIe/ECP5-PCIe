from ecp5_pcie.tlp import ConfigurationMemory, ConfigurationRequest, TLPType
from amaranth import *
from amaranth.sim import Simulator, Delay, Settle



if __name__ == "__main__":
    m = Module()

    request = ConfigurationRequest()
    new_request = Signal()
    m.submodules.cfgmem = cfgmem = ConfigurationMemory(ConfigurationMemory.make_init(0x1234, 0x5678), request, new_request)
    m.submodules.request = request


    sim = Simulator(m)

    sim.add_clock(1E-9, domain="rx")

    annotation = [
        "2x Device ID, 2x Vendor ID",
        "2x Status, 2x Command",
        "3x Class Code, Revision ID",
        "BIST, Header Type, Master Latency Timer, Cache Line Size",
        "BAR 0",
        "BAR 1",
        "BAR 2",
        "BAR 3",
        "BAR 4",
        "BAR 5",
        "CardBus",
        "2x Subsystem ID, 2x Subsystem Vendor ID",
        "Expansion ROM BAR",
        "3x Reserved, Capabilities Pointer",
        "Reserved",
        "Max_Lat, Min_Gnt, Interrupt Pin, Interrupt Line",

        "2x PCIe Capabilities, Next Capability Pointer, Capability ID",
        "Device Capabilties",
        "2x Device Status, 2x Device Control",
        "Link Capabilities",
        "2x Link Status, 2x Link Control",
        "Slot Capabilities",
        "2x Slot Status, 2x Slot Control",
        "2x Root Capabilities, 2x Root Control",
        "Root Status",
        "Device Capabilties 2",
        "2x Device Status 2, 2x Device Control 2",
        "Link Capabilities 2",
        "2x Link Status 2, 2x Link Control 2",
        "Slot Capabilities 2",
        "2x Slot Status 2, 2x Slot Control 2",
    ]

    def process():
        print("      \033[92m+0 +1 +2 +3")
        for i in range(256):
            yield request.tlp_type.eq(TLPType.CfgRd0)
            yield request.length.eq(1)
            yield request.first_dw_be.eq(0b1111)
            if i % 4 == 0:
                yield new_request.eq(1)
                yield cfgmem.configuration_request.register_number.eq(i // 4)
            if i % 4 == 3:
                yield new_request.eq(0)
                print("\033[97m0x\033[91m" + hex((i - 3) | 0x1000)[3:], end=" ")
                sn1 = "93"
                sn2 = "90"
                for j in range(4):
                    k = 3 - j
                    val = yield cfgmem.configuration_completion.configuration_data[k]
                    print(f"\033[{sn1 if val else sn2}m" + hex(0x100 | val)[3:], end=" ")
                print("\033[97m" + (annotation[i // 4] if i // 4 < len(annotation) else ""))

            yield

    sim.add_sync_process(process, domain="rx")

    with sim.write_vcd("test_cfgmem.vcd", "test_cfgmem.gtkw"):
        sim.run()