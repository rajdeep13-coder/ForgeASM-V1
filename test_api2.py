"""Debug the API loading issue."""
from core.isa.isa_def import ISA
from core.assembler.assembler import Assembler
from core.memory.memory import VonNeumannMemory
from core.io.io import MemoryMappedIO
from core.simulator.cpu import CPU
from api.simulation_manager import _load_binary_into_memory, Simulation

# Simulate exactly what the API does
isa_name = "risc1"
isa = ISA(isa_name)
asm = Assembler(isa)
code = "MOV $72\nOUT $1\nMOV $105\nOUT $1\nMOV $33\nOUT $1\nHALT"
binary = asm.assemble(code)

print("Binary string repr:")
print(repr(binary))
print()

# Check what _load_binary_into_memory does
lines = [ln.strip() for ln in binary.strip().split("\n") if ln.strip()]
print("Lines:", lines)
bit_stream = "".join(lines)
print("Bit stream length:", len(bit_stream))
print("First 36 bits:", bit_stream[:36])
print("Bits 0-5 (opcode of instr 0):", bit_stream[0:6])   # should be 100010 (mov)
print("Bits 18-23 (opcode of instr 1 at PC=3):", bit_stream[18:24])  # should be 101011 (out)
print("Bits 36-41 (opcode of instr 2 at PC=6):", bit_stream[36:42])  # should be 100010 (mov)
print()

# Now check what the CPU reads at PC=3
mem = VonNeumannMemory()
io_sys = MemoryMappedIO(mem)
cpu = CPU(isa, mem, io_sys)
_load_binary_into_memory(cpu, binary, 0)

print("Memory bytes 0-8:")
for i in range(9):
    b = cpu.memory.read_instr(i, 1)
    print(f"  byte[{i}] = {b:08b} ({b})")

print()
print("CPU reads at PC=0:")
bit_offset = 0 * 6
print(f"  bit_offset={bit_offset}")
bits = cpu._read_bits(bit_offset, 18)
print(f"  18 bits: {bits}")
print(f"  opcode: {bits[:6]}")

print()
print("CPU reads at PC=3:")
bit_offset = 3 * 6
print(f"  bit_offset={bit_offset}")
bits = cpu._read_bits(bit_offset, 18)
print(f"  18 bits: {bits}")
print(f"  opcode: {bits[:6]}")

# Check isa lookup
opcode_at_3 = bits[:6]
inst = isa.get_instruction_by_opcode(opcode_at_3)
print(f"  instruction: {inst.name if inst else 'NOT FOUND'}")

# Step through
cpu2 = CPU(isa, mem, io_sys)
_load_binary_into_memory(cpu2, binary, 0)
print()
print("Step trace:")
for i in range(10):
    if cpu2.halted: 
        print(f"  HALTED")
        break
    pc = cpu2.get_pc()
    bit_offset = pc * 6
    bits = cpu2._read_bits(bit_offset, 6)
    inst = isa.get_instruction_by_opcode(bits)
    print(f"  PC={pc} opcode={bits} instr={inst.name if inst else '???'}", end=" ")
    cpu2.step()
    print(f"→ PC={cpu2.get_pc()} output='{cpu2.output_buffer}'")
