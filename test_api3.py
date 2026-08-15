"""Debug simulation creation."""
import json, urllib.request

BASE = "http://127.0.0.1:8000"

def api(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

# Assemble
asm_res = api("POST", "/api/assemble", {
    "code": "MOV $72\nOUT $1\nMOV $105\nOUT $1\nMOV $33\nOUT $1\nHALT",
    "isa": "risc1"
})
binary = asm_res["binary"]
print("Binary lines:", binary.strip().split('\n'))
print("Binary repr:", repr(binary))
print()

# Create simulation
sim = api("POST", "/api/simulations", {
    "isa": "risc1",
    "memory_architecture": "neumann",
    "binary": binary
})
sim_id = sim["simulation_id"]
state0 = sim["state"]
print(f"Initial state: PC={state0['pc']} output='{state0['output']}' current_instr='{state0['current_instruction']}'")
print(f"Registers: {state0['registers']}")
print(f"Memory[0:8]: {state0['memory'][:8]}")
print()

# Check what instruction is at PC=0 according to memory
mem = state0['memory']
byte0 = mem[0]
print(f"byte[0] = {byte0:08b} = {byte0}")
print(f"First 6 bits = {byte0:08b}[:6] = {byte0 >> 2:06b}")  # top 6 bits of byte[0]

# Step 1
s1 = api("POST", f"/api/simulations/{sim_id}/step")
print(f"\nStep 1: last_instr='{s1['last_instruction']}' PC={s1['state']['pc']} output='{s1['state']['output']}'")
print(f"  current_instr='{s1['state']['current_instruction']}'")
print(f"  Memory[0:4]: {s1['state']['memory'][:4]}")

# Step 2
s2 = api("POST", f"/api/simulations/{sim_id}/step")
print(f"\nStep 2: last_instr='{s2['last_instruction']}' PC={s2['state']['pc']} output='{s2['state']['output']}'")

# Step 3
s3 = api("POST", f"/api/simulations/{sim_id}/step")
print(f"\nStep 3: last_instr='{s3['last_instruction']}' PC={s3['state']['pc']} output='{s3['state']['output']}'")
