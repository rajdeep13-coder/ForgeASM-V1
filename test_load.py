"""Test binary loading directly using exact same objects as Simulation."""
from api.simulation_manager import Simulation, _load_binary_into_memory

binary = '100010000001001000\n101011000000000001\n100010000001101001\n101011000000000001\n100010000000100001\n101011000000000001\n000000'

# Replicate exactly what Simulation.__init__ does
sim = Simulation(
    simulation_id="test",
    isa_name="risc1",
    memory_architecture="neumann",
    binary=binary,
    program_start=0,
)

cpu = sim.cpu
print("Memory bytes 0-8 via Simulation:")
for i in range(9):
    b = cpu.memory.read_data(i, 1)
    print(f"  byte[{i}] = {b:08b} = {b}")

print()
print("CPU reads at PC=3:")
bits = cpu._read_bits(3 * 6, 18)
print(f"  18 bits: {bits}")
print(f"  opcode: {bits[:6]}")

from core.isa.isa_def import ISA
isa = ISA("risc1")
inst = isa.get_instruction_by_opcode(bits[:6])
print(f"  instruction: {inst.name if inst else 'NOT FOUND'}")
