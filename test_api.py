"""End-to-end API pipeline test for Hi! and SUB zero."""
import json, urllib.request, urllib.error

BASE = "http://127.0.0.1:8000"

def api(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()}

print("=" * 60)
print("API TEST 1: Hi! program full pipeline")
print("=" * 60)

# Assemble
asm_res = api("POST", "/api/assemble", {"code": "MOV $72\nOUT $1\nMOV $105\nOUT $1\nMOV $33\nOUT $1\nHALT", "isa": "risc1"})
assert asm_res.get("success"), f"Assembly failed: {asm_res}"
binary = asm_res["binary"]
print(f"✓ Assemble: {len(binary.strip().split(chr(10)))} lines")

# Create simulation
sim = api("POST", "/api/simulations", {"isa": "risc1", "memory_architecture": "neumann", "binary": binary})
sim_id = sim["simulation_id"]
state0 = sim["state"]
print(f"✓ Create sim: id={sim_id[:8]}... PC={state0['pc']} output='{state0['output']}'")

# Step 7 times (7 instructions)
for i in range(7):
    step = api("POST", f"/api/simulations/{sim_id}/step")
    s = step["state"]
    print(f"  Step {i+1}: PC={s['pc']} output='{s['output']}' halted={s['halted']} instr='{step.get('last_instruction')}'")

# Final state check
final = api("GET", f"/api/simulations/{sim_id}")
fs = final["state"]
print(f"✓ Final: output='{fs['output']}' halted={fs['halted']} cycles={fs['cycle_count']}")
assert fs["output"] == "Hi!", f"FAIL: expected 'Hi!' got '{fs['output']}'"
assert fs["halted"], "FAIL: expected halted=True"
print("✓ PASS: output == 'Hi!' and halted")

# Reset
reset = api("POST", f"/api/simulations/{sim_id}/reset")
rs = reset["state"]
print(f"✓ Reset: output='{rs['output']}' PC={rs['pc']} cycles={rs['cycle_count']}")
assert rs["output"] == "", f"FAIL: after reset output should be '' got '{rs['output']}'"
assert rs["pc"] == 0, f"FAIL: after reset PC should be 0"
assert rs["cycle_count"] == 0
print("✓ PASS: reset clears output, PC, cycles")

# Run (full execution)
sim2 = api("POST", "/api/simulations", {"isa": "risc1", "memory_architecture": "neumann", "binary": binary})
sim_id2 = sim2["simulation_id"]
run = api("POST", f"/api/simulations/{sim_id2}/run", {"max_cycles": 1000})
rs2 = run["state"]
print(f"✓ Run: output='{rs2['output']}' cycles={run['cycles_executed']} reason={run['halt_reason']}")
assert rs2["output"] == "Hi!", f"FAIL: run output expected 'Hi!' got '{rs2['output']}'"
print("✓ PASS: run output == 'Hi!'")

print()
print("=" * 60)
print("API TEST 2: SUB zero Z flag")
print("=" * 60)

asm2 = api("POST", "/api/assemble", {"code": "MOV $10\nMOV $10\nSUB\nHALT", "isa": "risc1"})
assert asm2["success"]
sim3 = api("POST", "/api/simulations", {"isa": "risc1", "memory_architecture": "neumann", "binary": asm2["binary"]})
run3 = api("POST", f"/api/simulations/{sim3['simulation_id']}/run", {"max_cycles": 100})
state3 = run3["state"]
print(f"Flags: {state3['flags']}")
print(f"Registers: {state3['registers']}")
assert state3["flags"]["Z"] == True, f"FAIL: Z flag expected True got {state3['flags']['Z']}"
print("✓ PASS: Z flag = True after 10 SUB 10")

print()
print("=" * 60)
print("API TEST 3: Flags structure")
print("=" * 60)
assert "Z" in state3["flags"], "Missing Z flag"
assert "C" in state3["flags"], "Missing C flag"
assert "O" in state3["flags"], "Missing O flag"
assert "N" in state3["flags"], "Missing N flag"
print(f"✓ Flags present: {list(state3['flags'].keys())}")

print()
print("All API tests passed!")
