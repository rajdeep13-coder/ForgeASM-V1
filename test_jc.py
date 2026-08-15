"""Debug the helloworld demo jc issue."""
from core.isa.isa_def import ISA
from core.assembler.assembler import Assembler
from core.memory.memory import VonNeumannMemory
from core.io.io import MemoryMappedIO
from core.simulator.cpu import CPU
from api.simulation_manager import _load_binary_into_memory

with open('modules/demos/risc1/helloworld.asm') as f:
    demo_code = f.read()

isa = ISA('risc1')
asm = Assembler(isa)
binary = asm.assemble(demo_code)
print("Binary:")
for i, line in enumerate(binary.strip().split('\n')):
    print(f"  PC={i:2d}: {line}")

print()

mem = VonNeumannMemory()
io_sys = MemoryMappedIO(mem)
cpu = CPU(isa, mem, io_sys)
_load_binary_into_memory(cpu, binary, 0)

print("Step-by-step execution:")
for step_num in range(50):
    if cpu.halted:
        print(f"  HALTED at PC={cpu.get_pc()}")
        break
    
    pc = cpu.get_pc()
    tos_ptr = cpu.registers.get('TOS', 256)
    tos_val = cpu.memory.read_data(tos_ptr - 2, 2) if tos_ptr >= 258 else None
    fr = cpu.registers.get('FR', 0)
    z = cpu.get_flag('Z')
    c = cpu.get_flag('C')
    
    # Decode instruction name
    isa_bit_size = 6
    opcode_len = 6
    bit_offset = pc * isa_bit_size
    byte_idx = bit_offset // 8
    bit_rem = bit_offset % 8
    bits = ""
    for i in range(3):
        b = cpu.memory.read_instr(byte_idx + i, 1)
        bits += f"{b:08b}"
    opcode_str = bits[bit_rem: bit_rem + opcode_len]
    inst = isa.get_instruction_by_opcode(opcode_str)
    inst_name = inst.name if inst else '???'
    
    cpu.step()
    
    new_pc = cpu.get_pc()
    print(f"  Step {step_num+1:2d}: PC={pc:2d} [{inst_name:6s}] TOS_ptr={tos_ptr} TOS_val={tos_val} "
          f"Z={int(z)} C={int(c)} output='{cpu.output_buffer}' → new_PC={new_pc}")

print(f"\nFinal output: '{cpu.output_buffer}'")
