"""Quick verification tests for RISC1 CPU fixes."""
import sys
sys.path.insert(0, '.')

from core.isa.isa_def import ISA
from core.assembler.assembler import Assembler
from api.simulation_manager import Simulation

def test1():
    """RISC1 output 'Hi!'"""
    code = "mov $72\nout $1\nmov $105\nout $1\nmov $33\nout $1\nhalt"
    isa = ISA("risc1")
    binary = Assembler(isa).assemble(code)
    print(f"  Binary:\n{binary}")
    sim = Simulation("t1", "risc1", "neumann", binary, 0)
    cycles, reason = sim.run(max_cycles=200)
    state = sim.get_state()
    print(f"  output={repr(state.output)}, cycles={cycles}, reason={reason}")
    print(f"  registers={state.registers}")
    assert state.output == "Hi!", f"FAIL: expected 'Hi!' but got {repr(state.output)}"
    print("  TEST 1 PASSED ✓")

def test2():
    """RISC1 subtraction sets Z flag"""
    code = "mov $10\nmov $10\nsub\nhalt"
    isa = ISA("risc1")
    binary = Assembler(isa).assemble(code)
    print(f"  Binary:\n{binary}")
    sim = Simulation("t2", "risc1", "neumann", binary, 0)
    sim.run(max_cycles=100)
    state = sim.get_state()
    print(f"  flags={state.flags}, registers={state.registers}")
    assert state.flags["Z"] == True, f"FAIL: Z flag should be True, got {state.flags['Z']}"
    print("  TEST 2 PASSED ✓")

def test3():
    """RISC1 addition"""
    code = "mov $10\nmov $20\nadd\nhalt"
    isa = ISA("risc1")
    binary = Assembler(isa).assemble(code)
    print(f"  Binary:\n{binary}")
    sim = Simulation("t3", "risc1", "neumann", binary, 0)
    sim.run(max_cycles=100)
    state = sim.get_state()
    tos = state.registers.get("TOS", 0)
    from core.memory.memory import VonNeumannMemory
    print(f"  TOS={tos}, flags={state.flags}, registers={state.registers}")
    # TOS should be 258 (initial 256 + 2 for one value remaining = 258)
    # The result 30 should be at mem[TOS-2] = mem[256]
    assert tos == 258, f"FAIL: TOS should be 258 (one item on stack), got {tos}"
    print("  TEST 3 PASSED ✓")

def test4():
    """RISC1 alphabet printout demo"""
    with open("modules/demos/risc1/alphabet_printout.asm") as f:
        code = f.read()
    isa = ISA("risc1")
    binary = Assembler(isa).assemble(code)
    sim = Simulation("t4", "risc1", "neumann", binary, 0)
    cycles, reason = sim.run(max_cycles=5000)
    state = sim.get_state()
    print(f"  output={repr(state.output)}, cycles={cycles}, reason={reason}")
    assert state.output == "ABCDEFGHIJKLMNOPQRSTUVWXYZ", \
        f"FAIL: expected alphabet, got {repr(state.output)}"
    print("  TEST 4 PASSED ✓")

def test5():
    """RISC1 helloworld demo"""
    with open("modules/demos/risc1/helloworld.asm") as f:
        code = f.read()
    isa = ISA("risc1")
    binary = Assembler(isa).assemble(code)
    sim = Simulation("t5", "risc1", "neumann", binary, 0)
    cycles, reason = sim.run(max_cycles=5000)
    state = sim.get_state()
    print(f"  output={repr(state.output)}, cycles={cycles}, reason={reason}")
    expected = "Hello world!"
    assert state.output == expected, f"FAIL: expected {repr(expected)}, got {repr(state.output)}"
    print("  TEST 5 PASSED ✓")

print("=" * 60)
print("RISC1 CPU Tests")
print("=" * 60)

tests = [
    ("Test 1 - Hi! output", test1),
    ("Test 2 - Z flag after sub", test2),
    ("Test 3 - Addition TOS", test3),
    ("Test 4 - Alphabet printout", test4),
    ("Test 5 - Hello world", test5),
]

passed = 0
failed = 0
for name, fn in tests:
    print(f"\n{name}:")
    try:
        fn()
        passed += 1
    except Exception as e:
        print(f"  FAILED: {e}")
        import traceback
        traceback.print_exc()
        failed += 1

print(f"\n{'='*60}")
print(f"Results: {passed}/{passed+failed} passed")
