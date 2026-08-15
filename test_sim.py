"""Quick smoke tests for ForgeASM RISC1 simulator."""
import sys

# ── Test 1: Hi! program ────────────────────────────────────────────────────────
from core.isa.isa_def import ISA
from core.assembler.assembler import Assembler
from core.memory.memory import VonNeumannMemory
from core.io.io import MemoryMappedIO
from core.simulator.cpu import CPU
from api.simulation_manager import _load_binary_into_memory

def run_program(isa_name, code, max_cycles=200):
    isa = ISA(isa_name)
    asm = Assembler(isa)
    binary = asm.assemble(code)
    print(f"Binary ({isa_name}):")
    for i, line in enumerate(binary.strip().split('\n')):
        print(f"  [{i:2d}] {line}")

    mem = VonNeumannMemory()
    io_sys = MemoryMappedIO(mem)
    cpu = CPU(isa, mem, io_sys)
    _load_binary_into_memory(cpu, binary, 0)

    cycles = 0
    while not cpu.halted and cycles < max_cycles:
        cpu.step()
        cycles += 1

    return cpu, cycles

print("=" * 60)
print("TEST 1: RISC1 Hi! Program")
print("=" * 60)
code1 = """MOV $72
OUT $1
MOV $105
OUT $1
MOV $33
OUT $1
HALT"""
try:
    cpu, cycles = run_program('risc1', code1)
    print(f"Cycles: {cycles}")
    print(f"Halted: {cpu.halted}")
    print(f"Output: '{cpu.output_buffer}'")
    print(f"TOS:    {cpu.registers.get('TOS')}")
    print(f"FR:     {cpu.registers.get('FR')} (binary: {cpu.registers.get('FR', 0):016b})")
    print(f"IP:     {cpu.registers.get('IP')}")
    expected = "Hi!"
    if cpu.output_buffer == expected:
        print(f"✓ PASS: output == '{expected}'")
    else:
        print(f"✗ FAIL: expected '{expected}', got '{cpu.output_buffer}'")
except Exception as e:
    print(f"✗ ERROR: {e}")
    import traceback; traceback.print_exc()

print()
print("=" * 60)
print("TEST 2: RISC1 SUB zero (Z flag)")
print("=" * 60)
code2 = """MOV $10
MOV $10
SUB
HALT"""
try:
    cpu, cycles = run_program('risc1', code2)
    tos_addr = cpu.registers.get('TOS', 256)
    tos_val = cpu.memory.read_data(tos_addr - 2, 2)
    z_flag = cpu.get_flag('Z')
    n_flag = cpu.get_flag('N')
    print(f"Cycles: {cycles}, Halted: {cpu.halted}")
    print(f"TOS reg: {cpu.registers.get('TOS')}, TOS val: {tos_val}")
    print(f"Z={int(z_flag)} N={int(n_flag)} C={int(cpu.get_flag('C'))} O={int(cpu.get_flag('O'))}")
    if tos_val == 0 and z_flag:
        print("✓ PASS: TOS=0 and Z=1")
    else:
        print(f"✗ FAIL: expected TOS=0/Z=1, got TOS={tos_val}/Z={int(z_flag)}")
except Exception as e:
    print(f"✗ ERROR: {e}")
    import traceback; traceback.print_exc()

print()
print("=" * 60)
print("TEST 3: RISC1 ADD (10+20=30, no flags)")
print("=" * 60)
code3 = """MOV $10
MOV $20
ADD
HALT"""
try:
    cpu, cycles = run_program('risc1', code3)
    tos_addr = cpu.registers.get('TOS', 256)
    tos_val = cpu.memory.read_data(tos_addr - 2, 2)
    z_flag = cpu.get_flag('Z')
    print(f"TOS val: {tos_val}, Z={int(z_flag)}")
    if tos_val == 30 and not z_flag:
        print("✓ PASS: TOS=30, Z=0")
    else:
        print(f"✗ FAIL: expected TOS=30/Z=0, got TOS={tos_val}/Z={int(z_flag)}")
except Exception as e:
    print(f"✗ ERROR: {e}")
    import traceback; traceback.print_exc()

print()
print("=" * 60)
print("TEST 4: RISC1 helloworld.asm demo")
print("=" * 60)
try:
    with open('modules/demos/risc1/helloworld.asm') as f:
        demo_code = f.read()
    cpu, cycles = run_program('risc1', demo_code, max_cycles=5000)
    print(f"Cycles: {cycles}, Halted: {cpu.halted}")
    print(f"Output: '{cpu.output_buffer}'")
    if "Hello" in cpu.output_buffer:
        print("✓ PASS: output contains 'Hello'")
    else:
        print(f"✗ FAIL or PARTIAL: output = '{cpu.output_buffer}'")
except Exception as e:
    print(f"✗ ERROR: {e}")
    import traceback; traceback.print_exc()

print()
print("=" * 60)
print("TEST 5: RISC1 Step-by-step Hi!")
print("=" * 60)
code5 = """MOV $72
OUT $1
MOV $105
OUT $1
MOV $33
OUT $1
HALT"""
try:
    isa = ISA('risc1')
    asm = Assembler(isa)
    binary = asm.assemble(code5)
    mem = VonNeumannMemory()
    io_sys = MemoryMappedIO(mem)
    cpu = CPU(isa, mem, io_sys)
    _load_binary_into_memory(cpu, binary, 0)

    for i in range(10):
        if cpu.halted:
            break
        pc_before = cpu.get_pc()
        cpu.step()
        print(f"  Step {i+1}: PC {pc_before}→{cpu.get_pc()} | output='{cpu.output_buffer}' | TOS={cpu.registers.get('TOS')}")

    print(f"Final output: '{cpu.output_buffer}'")
    if cpu.output_buffer == "Hi!":
        print("✓ PASS")
    else:
        print(f"✗ FAIL: expected 'Hi!'")
except Exception as e:
    print(f"✗ ERROR: {e}")
    import traceback; traceback.print_exc()

print()
print("Done.")
