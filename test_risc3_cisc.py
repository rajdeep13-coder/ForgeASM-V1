"""Debug RISC3 and CISC issues."""
from core.isa.isa_def import ISA
from core.assembler.assembler import Assembler
from core.memory.memory import VonNeumannMemory
from core.io.io import MemoryMappedIO
from core.simulator.cpu import CPU
from api.simulation_manager import _load_binary_into_memory

def run_step_trace(isa_name, code, max_steps=40, title=""):
    print(f"{'='*60}")
    print(f"DEBUG: {title or isa_name}")
    print(f"{'='*60}")
    isa = ISA(isa_name)
    asm = Assembler(isa)
    try:
        binary = asm.assemble(code)
    except Exception as e:
        print(f"ASSEMBLE ERROR: {e}")
        import traceback; traceback.print_exc()
        return
    
    print("Binary:")
    for i, line in enumerate(binary.strip().split('\n')):
        print(f"  [{i:2d}] {line}")
    print()
    
    mem = VonNeumannMemory()
    io_sys = MemoryMappedIO(mem)
    cpu = CPU(isa, mem, io_sys)
    _load_binary_into_memory(cpu, binary, 0)
    
    isa_bit_size = {"risc1": 6, "risc2": 8, "risc3": 8, "cisc": 8}[isa_name]
    opcode_len_map = {"risc1": 6, "risc2": 8, "risc3": 6, "cisc": 8}
    
    for step in range(max_steps):
        if cpu.halted:
            print(f"  HALT at PC={cpu.get_pc()}")
            break
        
        pc = cpu.get_pc()
        opcode_len = opcode_len_map[isa_name]
        bit_offset = pc * isa_bit_size
        byte_idx = bit_offset // 8
        bit_rem = bit_offset % 8
        bits = ""
        for i in range(5):
            try:
                b = cpu.memory.read_instr(byte_idx + i, 1)
                bits += f"{b:08b}"
            except:
                bits += "00000000"
        opcode_str = bits[bit_rem: bit_rem + opcode_len]
        inst = isa.get_instruction_by_opcode(opcode_str)
        inst_name = inst.name if inst else f'???({opcode_str})'
        
        regs_str = " ".join(f"{k}={v}" for k, v in cpu.registers.items())
        cpu.step()
        print(f"  Step {step+1:2d}: PC={pc:3d}→{cpu.get_pc():3d} [{inst_name:10s}] out='{cpu.output_buffer}' [{regs_str}]")
    else:
        print(f"  MAX STEPS reached")
    
    print(f"\nFinal: output='{cpu.output_buffer}' halted={cpu.halted} PC={cpu.get_pc()}")
    print()


# RISC3 helloworld
with open('modules/demos/risc3/helloworld.asm') as f:
    code = f.read()
run_step_trace('risc3', code, max_steps=50, title="RISC3 helloworld")

# CISC alphabet_printout 
with open('modules/demos/cisc/alphabet_printout.asm') as f:
    code = f.read()
run_step_trace('cisc', code, max_steps=50, title="CISC alphabet_printout")
