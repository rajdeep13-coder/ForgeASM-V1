from core.memory.memory import MemorySystem
from core.memory.exceptions import MemoryAccessError

class IOSystem:
    def read_io(self, port: int) -> int:
        raise NotImplementedError
    def write_io(self, port: int, value: int):
        raise NotImplementedError
        
class MemoryMappedIO(IOSystem):
    def __init__(self, memory: MemorySystem, io_base_address: int = 0xFF00, size: int = 256):
        self.memory = memory
        self.io_base_address = io_base_address
        self.size = size
        self.ports = bytearray(size)
        
    def read_io(self, address: int) -> int:
        if self.io_base_address <= address < self.io_base_address + self.size:
            return self.ports[address - self.io_base_address]
        # otherwise delegate to memory
        return self.memory.read_data(address, 1) # simple byte fallback, usually intercept handled at CPU level
        
    def write_io(self, address: int, value: int):
        if self.io_base_address <= address < self.io_base_address + self.size:
            self.ports[address - self.io_base_address] = value & 0xFF
        else:
            self.memory.write_data(address, value, 1)

class PortMappedIO(IOSystem):
    def __init__(self, size: int = 256):
        self.ports = bytearray(size)
        
    def read_io(self, port: int) -> int:
        if 0 <= port < len(self.ports):
            return self.ports[port]
        raise MemoryAccessError(f"I/O Port {port} out of bounds")
        
    def write_io(self, port: int, value: int):
        if 0 <= port < len(self.ports):
            self.ports[port] = value & 0xFF
        else:
            raise MemoryAccessError(f"I/O Port {port} out of bounds")
