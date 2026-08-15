"""Test all ISA demos for regression."""
import os
from core.isa.isa_def import ISA
from core.assembler.assembler import Assembler
from core.memory.memory import VonNeumannMemory
from core.io.io import MemoryMappedIO
from core.simulator.cpu import CPU
from api.simulation_manager import _load_binary_into_memory

def run_program(isa_name, code, max_cycles=5000):
    isa = ISA(isa_name)
    asm = Assembler(isa)
    binary = asm.assemble(code)
    mem = VonNeumannMemory()
    io_sys = MemoryMappedIO(mem)
    cpu = CPU(isa, mem, io_sys)
    _load_binary_into_memory(cpu, binary, 0)
    cycles = 0
    while not cpu.halted and cycles < max_cycles:
        cpu.step()
        cycles += 1
    return cpu, cycles, binary

def test_demo(isa_name, prog_name):
    path = os.path.join('modules', 'demos', isa_name, f'{prog_name}.asm')
    if not os.path.exists(path):
        print(f"  SKIP: {path} not found")
        return
    with open(path) as f:
        code = f.read()
    try:
        cpu, cycles, binary = run_program(isa_name, code, max_cycles=10000)
        halted = "HALT" if cpu.halted else "MAX_CYCLES"
        print(f"  {halted:12s} {cycles:5d} cycles  output='{cpu.output_buffer[:50]}'")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()

print("=" * 60)
print("RISC1 DEMOS")
print("=" * 60)
for demo in ['helloworld', 'alphabet_printout']:
    print(f"  {demo}:")
    test_demo('risc1', demo)

print()
print("=" * 60)
print("RISC2 DEMOS")
print("=" * 60)
for demo in ['helloworld', 'alphabet_printout', 'bubble_sort']:
    print(f"  {demo}:")
    test_demo('risc2', demo)

print()
print("=" * 60)
print("RISC3 DEMOS")
print("=" * 60)
for demo in ['helloworld', 'alphabet_printout']:
    print(f"  {demo}:")
    test_demo('risc3', demo)

print()
print("=" * 60)
print("CISC DEMOS")
print("=" * 60)
for demo in ['helloworld', 'alphabet_printout', 'bubble_sort']:
    print(f"  {demo}:")
    test_demo('cisc', demo)

print()
print("=" * 60)
print("RISC1 UNIT TESTS")
print("=" * 60)

def unit_test(name, isa_name, code, check_fn):
    try:
        cpu, cycles, _ = run_program(isa_name, code)
        result = check_fn(cpu)
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")
        if not result:
            print(f"         output='{cpu.output_buffer}' Z={int(cpu.get_flag('Z'))} C={int(cpu.get_flag('C'))} halted={cpu.halted}")
    except Exception as e:
        print(f"  ✗ ERROR: {name}: {e}")

unit_test("Hi! output", "risc1",
    "MOV $72\nOUT $1\nMOV $105\nOUT $1\nMOV $33\nOUT $1\nHALT",
    lambda cpu: cpu.output_buffer == "Hi!")

unit_test("SUB zero Z=1", "risc1",
    "MOV $10\nMOV $10\nSUB\nHALT",
    lambda cpu: cpu.get_flag("Z"))

unit_test("ADD 10+20=30", "risc1",
    "MOV $10\nMOV $20\nADD\nHALT",
    lambda cpu: cpu.memory.read_data(cpu.registers.get('TOS', 256) - 2, 2) == 30)

unit_test("MUL 5*6=30", "risc1",
    "MOV $5\nMOV $6\nMUL\nHALT",
    lambda cpu: cpu.memory.read_data(cpu.registers.get('TOS', 256) - 2, 2) == 30)

unit_test("DIV 30/5=6", "risc1",
    "MOV $30\nMOV $5\nDIV\nHALT",
    lambda cpu: cpu.memory.read_data(cpu.registers.get('TOS', 256) - 2, 2) == 6)

unit_test("AND 0xFF & 0x0F = 0x0F", "risc1",
    "MOV $255\nMOV $15\nAND\nHALT",
    lambda cpu: cpu.memory.read_data(cpu.registers.get('TOS', 256) - 2, 2) == 15)

unit_test("OR 0xF0 | 0x0F = 0xFF", "risc1",
    "MOV $240\nMOV $15\nOR\nHALT",
    lambda cpu: cpu.memory.read_data(cpu.registers.get('TOS', 256) - 2, 2) == 255)

unit_test("XOR 0xFF ^ 0xFF = 0", "risc1",
    "MOV $255\nMOV $255\nXOR\nHALT",
    lambda cpu: cpu.get_flag("Z") and cpu.memory.read_data(cpu.registers.get('TOS', 256) - 2, 2) == 0)

unit_test("NOT ~0 = 0xFFFF", "risc1",
    "MOV $0\nNOT\nHALT",
    lambda cpu: cpu.memory.read_data(cpu.registers.get('TOS', 256) - 2, 2) == 65535)

unit_test("CMPE Z flag (equal)", "risc1",
    "MOV $10\nMOV $10\nCMPE\nHALT",
    lambda cpu: cpu.get_flag("Z"))

unit_test("JMP branch works", "risc1",
    "MOV $72\nJMP $3\nMOV $0\nOUT $1\nHALT",
    lambda cpu: cpu.output_buffer == "H")

print()
print("Done.")
