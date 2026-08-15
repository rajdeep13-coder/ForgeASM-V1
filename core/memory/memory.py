from typing import Union, List
from core.memory.exceptions import OutOfBoundsError

class MemoryBank:
    """A generic byte-addressable memory bank."""
    def __init__(self, size_bytes: int):
        self.size = size_bytes
        # Using a bytearray for efficient and simple 8-bit addressing
        self.data = bytearray(size_bytes)
        
    def read_byte(self, address: int) -> int:
        if 0 <= address < self.size:
            return self.data[address]
        raise OutOfBoundsError(f"Read address {address} out of bounds")
        
    def write_byte(self, address: int, value: int):
        if 0 <= address < self.size:
            self.data[address] = value & 0xFF
        else:
            raise OutOfBoundsError(f"Write address {address} out of bounds")
            
    def read_word(self, address: int) -> int:
        # Assuming little-endian for now, or we can make it configurable
        # Most of the original was acting sequentially on bitarrays. 
        # Since we use bytearray, let's stick to Big Endian as it's easier to read visually, or Little Endian.
        # Let's do Big Endian: high byte at address, low byte at address+1
        if 0 <= address < self.size - 1:
            return (self.data[address] << 8) | self.data[address+1]
        raise OutOfBoundsError(f"Read word address {address} out of bounds")
        
    def write_word(self, address: int, value: int):
        if 0 <= address < self.size - 1:
            self.data[address] = (value >> 8) & 0xFF
            self.data[address+1] = value & 0xFF
        else:
            raise OutOfBoundsError(f"Write word address {address} out of bounds")

class MemorySystem:
    def read_instr(self, address: int, num_bytes: int) -> int:
        raise NotImplementedError
    def read_data(self, address: int, num_bytes: int) -> int:
        raise NotImplementedError
    def write_data(self, address: int, value: int, num_bytes: int):
        raise NotImplementedError

class VonNeumannMemory(MemorySystem):
    def __init__(self, size_bytes: int = 65536):
        self.mem = MemoryBank(size_bytes)
        
    def read_instr(self, address: int, num_bytes: int) -> int:
        return self._read(address, num_bytes)
        
    def read_data(self, address: int, num_bytes: int) -> int:
        return self._read(address, num_bytes)
        
    def write_data(self, address: int, value: int, num_bytes: int):
        self._write(address, value, num_bytes)
        
    def _read(self, address: int, num_bytes: int) -> int:
        if num_bytes == 1:
            return self.mem.read_byte(address)
        elif num_bytes == 2:
            return self.mem.read_word(address)
        else:
            # Handle arbitrary bytes if needed (e.g. 16 bits = 2 bytes)
            val = 0
            for i in range(num_bytes):
                val = (val << 8) | self.mem.read_byte(address + i)
            return val
            
    def _write(self, address: int, value: int, num_bytes: int):
        if num_bytes == 1:
            self.mem.write_byte(address, value)
        elif num_bytes == 2:
            self.mem.write_word(address, value)
        else:
            for i in range(num_bytes):
                shift = (num_bytes - 1 - i) * 8
                self.mem.write_byte(address + i, (value >> shift) & 0xFF)

class HarvardMemory(MemorySystem):
    def __init__(self, instr_size: int = 32768, data_size: int = 32768):
        self.instr_mem = MemoryBank(instr_size)
        self.data_mem = MemoryBank(data_size)
        
    def read_instr(self, address: int, num_bytes: int) -> int:
        return self._read(self.instr_mem, address, num_bytes)
        
    def read_data(self, address: int, num_bytes: int) -> int:
        return self._read(self.data_mem, address, num_bytes)
        
    def write_data(self, address: int, value: int, num_bytes: int):
        self._write(self.data_mem, address, value, num_bytes)
        
    def _read(self, bank: MemoryBank, address: int, num_bytes: int) -> int:
        val = 0
        for i in range(num_bytes):
            val = (val << 8) | bank.read_byte(address + i)
        return val
        
    def _write(self, bank: MemoryBank, address: int, value: int, num_bytes: int):
        for i in range(num_bytes):
            shift = (num_bytes - 1 - i) * 8
            bank.write_byte(address + i, (value >> shift) & 0xFF)

class ModifiedHarvardMemory(VonNeumannMemory):
    # Separate instruction/data paths but shared physical memory.
    # In a functional simulator without caches, this behaves identically to Von Neumann.
    pass
