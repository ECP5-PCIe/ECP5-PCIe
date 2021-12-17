from amaranth import *
from amaranth.build import *
from enum import IntEnum
import math

class TLPType(IntEnum): # PCIe Base 1.1 Page 49
    # Value equals to Cat(type, fmt)
    MRd32   = 0b0000000 # 32 bit Memory Read Request
    MRd64   = 0b0100000 # 64 bit Memory Read Request
    MRdLk32 = 0b0000001 # 32 bit Locked Memory Read Request
    MRdLk64 = 0b0100001 # 64 bit Locked Memory Read Request
    MWr32   = 0b1000000 # 32 bit Memory Write Request
    MWr64   = 0b1100000 # 64 bit Memory Write Request
    IORd    = 0b0000010 # I/O Read Request
    IOWr    = 0b1000010 # I/O Write Request
    CfgRd0  = 0b0000100 # Configuration Read Type 0
    CfgWr0  = 0b1000100 # Configuration Write Type 0
    CfgRd1  = 0b0000101 # Configuration Read Type 1
    CfgWr1  = 0b1000101 # Configuration Write Type 1
    Msg     = 0b0110000 # Message Request, last 3 bits give message routing type
    MsgD    = 0b1110000 # Message Request with data payload, last 3 bits give message routing type
    Cpl     = 0b0001010 # Completion without Data
    CplD    = 0b1001010 # Completion with Data
    CplLk   = 0b0001011 # Completion for Locked Memory Read without Data (error)
    CplDLk  = 0b1001011 # Completion for Locked Memory Read with Data

class TLPBase(Elaboratable):
    def __init__(self):
        self.fmt      = Signal( 2)
        """TLP format"""
        self.type     = Signal( 5)
        """TLP type"""
        self.tlp_type = Cat(self.type, self.fmt)
        """Equivalent to value in Type IntEnum"""
        self.tc       = Signal( 3)
        """Traffic class"""
        self.td       = Signal(  )
        """TLP digest present"""
        self.ep       = Signal(  )
        """TLP poisoned"""
        self.attr     = Signal( 2)
        """Attributes"""
        self.length   = Signal(10)
        """Length in number of DW / 4 bytes / 32 bits"""


class MemoryIORequest(TLPBase):
    def __init__(self):
        super().__init__()
        self.requester_id = Signal(16)
        self.tag = Signal(8)
        self.last_dw_be = Signal(4)
        self.first_dw_be = Signal(4)
        self.address = Signal(64)

        self.data = [Signal(8) for i in range(4 * 4)]

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        data = self.data

        m.d.comb += [
            self.fmt.eq(data[0][5:7]),
            self.type.eq(data[0][0:5]),
            self.tc.eq(data[1][4:7]),
            self.td.eq(data[2][7]),
            self.ep.eq(data[2][6]),
            self.attr.eq(data[2][4:6]),
            self.length.eq(Cat(data[3], data[2][0:2])),
            self.requester_id.eq(Cat(data[5], data[4])),
            self.tag.eq(Cat(data[6])),
            self.last_dw_be.eq(data[7][4:8]),
            self.first_dw_be.eq(data[7][0:4]),
        ]

        with m.If(self.fmt[0]):
            m.d.comb += self.address[2:].eq(Cat(data[8:16][::-1]))
        with m.Else():
            m.d.comb += self.address[2:].eq(Cat(data[8:12][::-1]))

        return m


class ConfigurationRequest(TLPBase):
    def __init__(self):
        super().__init__()
        self.requester_id = Signal(16)
        self.tag = Signal(8)
        self.last_dw_be = Signal(4)
        self.first_dw_be = Signal(4)

        self.bus_number = Signal(8)
        self.device_number = Signal(5)
        self.function_number = Signal(3)
        self.completer_id = Cat(self.function_number, self.device_number, self.bus_number)
        self.extended_register_number = Signal(4)
        self.register_number = Signal(6)
        self.register = Cat(self.register_number, self.extended_register_number)
        self.configuration_data = [Signal(8, name = f"Cfg_Req_Data_{i}") for i in range(4)]

        self.data = [Signal(8) for i in range(4 * 4)]

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        data = self.data

        m.d.comb += [
            self.fmt.eq(data[0][5:7]),
            self.type.eq(data[0][0:5]),
            self.tc.eq(data[1][4:7]),
            self.td.eq(data[2][7]),
            self.ep.eq(data[2][6]),
            self.attr.eq(data[2][4:6]),
            self.length.eq(Cat(data[3], data[2][0:2])),
            self.requester_id.eq(Cat(data[5], data[4])),
            self.tag.eq(Cat(data[6])),
            self.last_dw_be.eq(data[7][4:8]),
            self.first_dw_be.eq(data[7][0:4]),

            self.bus_number.eq(data[8]),
            self.device_number.eq(data[9][3:8]),
            self.function_number.eq(data[9][0:3]),
            self.extended_register_number.eq(data[10][0:4]),
            self.register_number.eq(data[11][2:8]),
            
            self.configuration_data[0].eq(data[12]), # TODO: Is this ordered right?
            self.configuration_data[1].eq(data[13]),
            self.configuration_data[2].eq(data[14]),
            self.configuration_data[3].eq(data[15]),
        ]

        return m


class MessageRequest(TLPBase):
    def __init__(self):
        super().__init__()
        self.requester_id = Signal(16)
        self.tag = Signal(8)
        self.message_code = Signal(8)

        self.data = [Signal(8) for i in range(4 * 4)]

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        data = self.data

        m.d.comb += [
            self.fmt.eq(data[0][5:7]),
            self.type.eq(data[0][0:5]),
            self.tc.eq(data[1][4:7]),
            self.td.eq(data[2][7]),
            self.ep.eq(data[2][6]),
            self.attr.eq(data[2][4:6]),
            self.length.eq(Cat(data[3], data[2][0:2])),
            self.requester_id.eq(Cat(data[5], data[4])),
            self.tag.eq(Cat(data[6])),
            self.message_code.eq(data[7]),
        ]

        return m


class ConfigurationReadCompletion(TLPBase):
    def __init__(self):
        super().__init__()
        self.requester_id = Signal(16)
        self.tag = Signal(8)

        self.completer_id = Signal(16)
        self.completion_status = Signal(3)
        self.bcm = Const(1, 1)
        self.byte_count = Signal(12)
        self.lower_address = Const(0, 7)

        self.configuration_data = [Signal(8, name = f"Cfg_Cpl_Data_{i}") for i in range(4)]

        self.data = [Signal(8) for i in range(4 * 4)]

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        data = self.data

        m.d.comb += Cat(self.data).eq(Cat(
            self.type,
            self.fmt,
            Const(0, 1),

            Const(0, 4),
            self.tc,
            Const(0, 1),

            self.length[8:10],
            Const(0, 2),
            self.attr,
            self.ep,
            self.td,

            self.length[0:8],

            self.completer_id[8:16],
            self.completer_id[0:8],

            self.byte_count[8:12],
            self.bcm,
            self.completion_status,

            self.requester_id[8:16],
            self.requester_id[0:8],
            self.tag,
            self.lower_address,
            Const(0, 1),
        ))

        return m


class ConfigurationMemory(Elaboratable):
    """
    Configuration memory
    
    Parameters
    ----------
    init : int
        Init values, use make_init to generate it

    configuration_request : ConfigurationRequest
        Configuration Request to take data from

    new_request : Signal
        Toggle to process configuration request

    ratio : int
        Gearbox ratio
    """
    def __init__(self, init: list[int], configuration_request: ConfigurationRequest, new_request: Signal, ratio = 4):
        self.ratio = ratio
        assert 4096 // ratio == 4096 / ratio # Ratio needs to be 2 ** n
        assert ratio >= 4 # And at least 4
        self.init = init
        self.configuration_request = configuration_request
        self.configuration_completion = ConfigurationReadCompletion()
        self.new_request = new_request
        self.done = Signal() # Is high for 1 cycle

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        ratio = self.ratio

        memory_init = [int.from_bytes(self.init[i : i + ratio], byteorder = "little") for i in range(0, len(self.init), self.ratio)]
        assert len(memory_init) == len(self.init) / ratio

        # TODO: Considering that always 4 bytes are processed having a variable width memory is nonsense
        memory = Memory(width = 8 * self.ratio, depth = 4096 // self.ratio, init = memory_init, name = "Configuration_Memory")
        m.submodules.read_port = read_port = memory.read_port(domain = "rx", transparent = False)
        m.submodules.write_port = write_port = memory.write_port(domain = "rx", granularity = 8)
        m.submodules += self.configuration_completion

        m.d.rx += read_port.en.eq(1)
        m.d.rx += write_port.en.eq(0)
        m.d.rx += self.done.eq(0)

        # TODO: Make an LTSSM which processes any pending TLPs and refreshes status registers as required
        with m.FSM(name = "Configuration_FSM", domain = "rx"):
            with m.State("Idle"):
                with m.If(self.new_request):
                    m.d.comb += read_port.addr.eq(self.configuration_request.register.shift_right(self.ratio // 4 - 1))
                    m.next = "Process"
            
            with m.State("Process"):
                with m.If(self.configuration_request.tlp_type == TLPType.CfgRd0):
                    m.d.rx += [ # TODO: Is this the right amount of delay?
                        self.configuration_completion.configuration_data[i].eq(
                            read_port.data.word_select(i | (self.configuration_request.register & int(math.log2(ratio // 4))).shift_left(2), 8)
                            )
                        for i in range(4)]
                    
                    m.d.rx += [
                        self.configuration_completion.completer_id.eq(self.configuration_request.completer_id),
                        self.configuration_completion.requester_id.eq(self.configuration_request.requester_id),
                        self.configuration_completion.tag.eq(self.configuration_request.tag),
                        self.configuration_completion.byte_count.eq(4), # TODO: Eh, this might cause errors when byte enables are set
                        self.configuration_completion.tlp_type.eq(TLPType.CplD),
                        self.configuration_completion.length.eq(self.configuration_request.first_dw_be.any()),
                    ]

                with m.Elif(self.configuration_request.tlp_type == TLPType.CfgWr0):
                    m.d.rx += write_port.addr.eq(self.configuration_request.register.shift_right(self.ratio // 4))
                    m.d.rx += write_port.en.eq(self.configuration_request.first_dw_be | (self.configuration_request.register & int(math.log2(ratio // 4))).shift_left(2))
                    m.d.rx += write_port.data.eq(Repl(Cat(self.configuration_request.data), self.ratio // 4))
                
                m.d.rx += self.done.eq(1)
                m.next = "Idle"

        return m

    @staticmethod
    def make_init(vendor_id: int, device_id: int, subsystem_vendor_id: int = 0, subsystem_device_id: int = 0, command: int = 0, status: int = 0x0010, max_payload_size = 128):
        """
        Make init values
        
        Parameters
        ----------
        vendor_id : int
            Vendor ID, 16 bits, assigned by chipset manufacturer

        device_id : int
            Device ID, 16 bits

        subsystem_vendor_id : int
            Subsystem Vendor ID, 16 bits, assigned by card manufacturer

        subsystem_device_id : int
            Device ID, 16 bits
        """
        def get_bytes(val, n):
            return val.to_bytes(n, byteorder = "little")

        init = [
            *get_bytes(vendor_id, 2),           # 00
            *get_bytes(device_id, 2),           # 02
            *get_bytes(command, 2),             # 04
            *get_bytes(status, 2),              # 06
            0x00, 0x00, 0x00, 0x00,             # 08 Revision ID, Class Code
            0x00, 0x00, 0x00, 0x00,             # 0C Cache Line Size (init = 0x00), Master Latency Timer (hardwired to 0x00), Header Type, BIST
            0x00, 0x00, 0x00, 0x00,             # 10 BAR 0
            0x00, 0x00, 0x00, 0x00,             # 14 BAR 1
            0x00, 0x00, 0x00, 0x00,             # 18 BAR 2
            0x00, 0x00, 0x00, 0x00,             # 1C BAR 3
            0x00, 0x00, 0x00, 0x00,             # 20 BAR 4
            0x00, 0x00, 0x00, 0x00,             # 24 BAR 5
            0x00, 0x00, 0x00, 0x00,             # 28 CardBus
            *get_bytes(subsystem_vendor_id, 2), # 2C
            *get_bytes(subsystem_device_id, 2), # 2E
            0x00, 0x00, 0x00, 0x00,             # 30 Expansion ROM Base Address, can be used to execute instructions during boot, assigned by host(?)
            0x00, 0x00, 0x00, 0x00,             # 34 Capabilities Pointer, automatically assigned
            0x00, 0x00, 0x00, 0x00,             # 38 Reserved
            0x00, 0x00, 0x00, 0x00,             # 3C Interrupt Line, Interrupt Pin, Min_Gnt, Max_Lat
            *[0x00 for _ in range(0x1000 - 0x40)]
        ]

        pcie_capabilities = 0
        pcie_capabilities |= 0x2 << 0 # Capability version 2, see PCIe Base 3.0 page 606
        pcie_capabilities |= 0b0 << 4 # PCIe endpoint
        pcie_capabilities |= 0b0 << 8 # Slot implemented, set to 1 if device is in a slot
        pcie_capabilities |= 0x0 << 9 # Interrupt message number

        max_payload_size_dict = {128: 0, 256: 1, 512: 2, 1024: 3, 2048: 4, 4096: 5}

        device_capabilities = 0
        device_capabilities |= max_payload_size_dict[max_payload_size] << 0 # Max_Payload_Size
        device_capabilities |= 0b00 << 3 # Phantom Functions
        device_capabilities |= 0b0 << 5 # Extended Tag Field
        device_capabilities |= 0b000 << 6 # Endpoint L0s Acceptable Latency
        device_capabilities |= 0b000 << 9 # Endpoint L1 Acceptable Latency
        device_capabilities |= 0b000 << 12 # Undefined
        device_capabilities |= 0b0 << 15 # Role-Based Error Reporting
        device_capabilities |= 0 << 18 # Captured Slot Power Limit Value, set by Set_Slot_Power_Limit Message
        device_capabilities |= 0b00 << 26 # Captured Slot Power Limit Scale
        device_capabilities |= 0b0 << 28 # Function Level Reset Capability

        device_control = 0
        device_control |= 0b1 << 4 # Enable Relaxed Ordering, default 0b1
        device_control |= 0b000 << 5 # Max_Payload_Size, default 0b000
        device_control |= 0b0 << 8 # Whether 8 bit tag fields are allowed, default is implementation specific
        device_control |= 0b010 << 12 # Max_Read_Request_Size, default 0b010, but 0b000 read only is allowed if device doesn't make read requests larger than 128 B

        device_status = 0

        link_capabilities = 0
        link_capabilities |= 0b0001 << 0 # Max Link Speed, 2.5 GT/s is 0001 and 5 GT/s is 0010
        link_capabilities |= 0b000001 << 4 # Maximum Link Width, x1
        link_capabilities |= 0b00 << 10 # Active State Power Management (ASPM) Support, whether L0s and L1 is supported (0b01 = L0s, 0b10 = L1, 0b11 = 0b01 | 0b10)
        link_capabilities |= 0b111 << 12 # L0s Exit Latency
        link_capabilities |= 0b111 << 15 # L1 Exit Latency
        link_capabilities |= 0b1 << 22 # ASPM Optionality Compliance, must be set to 0b1
        link_capabilities |= 0b00000000 << 24 # Port Number, TODO: Does this need to be set in the LTSSM when the port is negotiated?

        link_control = 0 # TODO: If bit 5 is set it should retrain the LTSSM, though apparently it is reserved for endpoints
        link_control |= 0b0 << 6 # Common Clock Configuration, if 1 this means that the clocks are synchronized. TODO: Does this affect Spread Spectrum Clocking (SSC)?

        link_status = 0
        link_status |= 0b0001 << 0 # 2.5 GT/s, TODO: This should be set by the LTSSM, at least for transition to 5 GT/s
        link_status |= 0b000001 << 4 # Link width x1 TODO: set by LTSSM
        link_status |= 0b0 << 12 # Use shared reference clock = 0b1


        device_capabilities_2 = 0 
        device_capabilities_2 |= 0b0000 << 0 # Completion Timeout Ranges Supported, whether the completion timeout can be set, in this case 50 µs to 50 ms
        device_capabilities_2 |= 0b0 << 4 # Completion Timeout Disable Supported

        device_control_2 = 0

        device_status_2 = 0 # Placeholder in PCIe Base 3.0

        link_capabilities_2 = 0
        link_capabilities_2 |= 0b001 << 1 # Supported Link Speeds, 8.0, 5.0 and 2.5 GT/s

        link_control_2 = 0

        link_status_2 = 0

        capabilities = [ # List of capabilities
            [
                0x10,                                 # 00 PCI Express Capability
                0x00,                                 # 01 Next Capability Pointer, 0 indicates that this is the end of the list, automatically assigned
                *get_bytes(pcie_capabilities, 2),     # 02
                *get_bytes(device_capabilities, 4),   # 04
                *get_bytes(device_control, 2),        # 08
                *get_bytes(device_status, 2),         # 0A
                *get_bytes(link_capabilities, 4),     # 0C
                *get_bytes(link_control, 2),          # 10
                *get_bytes(link_status, 2),           # 12
                0x00, 0x00, 0x00, 0x00,               # 14 Slot Capabilities
                0x00, 0x00, 0x00, 0x00,               # 18 Slot Control / Status
                0x00, 0x00, 0x00, 0x00,               # 1C Root Control / Capabilities
                0x00, 0x00, 0x00, 0x00,               # 20 Root Status
                *get_bytes(device_capabilities_2, 4), # 24
                *get_bytes(device_control_2, 2),      # 28
                *get_bytes(device_status_2, 2),       # 2A
                *get_bytes(link_capabilities_2, 4),   # 2C
                *get_bytes(link_control_2, 2),        # 30
                *get_bytes(link_status_2, 2),         # 32
                0x00, 0x00, 0x00, 0x00,               # 34 Slot Capabilities 2
                0x00, 0x00, 0x00, 0x00,               # 38 Slot Control 2 / Status 2
            ]
        ]

        current_pointer = 0x40 # Start at 0x40

        init[0x34] = current_pointer # Set first capability pointer

        for i, capability in enumerate(capabilities):
            next_pointer = current_pointer + len(capability)

            if i == len(capabilities) - 1:
                next_location = 0x00
            else:
                next_location = next_pointer

            capability[1] = next_location # 01 is the next capability pointer

            init[current_pointer : current_pointer + len(capability)] = capability

            assert next_pointer <= 0x100 # Here the extended capability space starts
            current_pointer = next_pointer

        return init


class TLPGenerator(Elaboratable):
    def __init__(self, ratio = 4):
        self.tlp_source = StreamInterface(8, ratio, name="TLP_Gen_Source")
        self.ratio = ratio

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        ratio = self.ratio

        timer = Signal(9)

        with m.If(self.tlp_source.ready):
            m.d.rx += timer.eq(timer + 1)
            with m.If(timer < 128): # TODO: If this value is 64 it goes to Recovery
                for i in range(ratio):
                    m.d.rx += self.tlp_source.symbol[i].eq(timer * ratio + i)
                    m.d.rx += self.tlp_source.valid[i].eq(1)

            with m.Else():
                for i in range(ratio):
                    m.d.rx += self.tlp_source.valid[i].eq(0)



        return m