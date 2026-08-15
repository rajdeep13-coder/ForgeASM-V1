import json
import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from core.isa.isa_def import ISA
from core.assembler.assembler import Assembler
from core.memory.memory import VonNeumannMemory, HarvardMemory
from core.io.io import MemoryMappedIO
from core.simulator.cpu import CPU

app = FastAPI(title="ForgeASM — Hardware Simulator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Models ──────────────────────────────────────────────────────────

class AssembleRequest(BaseModel):
    code: str
    isa: str

class AssembleResponse(BaseModel):
    binary: str
    error: Optional[str] = None
    success: bool


# ─── Assemble Endpoint ───────────────────────────────────────────────

@app.post("/api/assemble", response_model=AssembleResponse)
async def assemble_code(req: AssembleRequest):
    try:
        isa = ISA(req.isa.lower())
        assembler = Assembler(isa)
        binary = assembler.assemble(req.code)
        return AssembleResponse(binary=binary, success=True)
    except Exception as e:
        return AssembleResponse(binary="", error=str(e), success=False)


# ─── ISA Info Endpoint ───────────────────────────────────────────────

@app.get("/api/isa/{name}")
async def get_isa_info(name: str):
    """Return instruction set and register definitions for a given ISA."""
    try:
        isa = ISA(name.lower())
        registers = []
        for reg in isa.registers.values():
            registers.append({
                "name": reg.name,
                "is_general_purpose": reg.is_general_purpose,
                "encoding": reg.encoding,
                "description": reg.description,
            })
        instructions = []
        for opcode, inst in isa.instructions.items():
            instructions.append({
                "opcode": opcode,
                "name": inst.name,
                "result_dest": inst.result_dest,
                "operands": inst.operands,
            })
        return {
            "name": isa.name,
            "registers": registers,
            "instructions": instructions,
        }
    except Exception as e:
        return {"error": str(e)}


# ─── Example Programs Endpoint ───────────────────────────────────────

@app.get("/api/examples")
async def get_examples():
    """Return example assembly programs for each ISA."""
    isas = ["risc1", "risc2", "risc3", "cisc"]
    program_names = ["alphabet_printout", "helloworld", "bubble_sort", "polynomial"]
    examples: Dict[str, List[Dict[str, str]]] = {}

    base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules", "demos")

    for isa_name in isas:
        isa_examples = []
        for prog in program_names:
            filepath = os.path.join(base_dir, isa_name, f"{prog}.asm")
            try:
                with open(filepath, "r") as f:
                    code = f.read()
                display_name = prog.replace("_", " ").title()
                isa_examples.append({"name": display_name, "code": code})
            except FileNotFoundError:
                pass
        examples[isa_name] = isa_examples

    return examples


# ─── WebSocket Simulation Endpoint ───────────────────────────────────

def load_binary_to_memory(cpu: CPU, binary_str: str, program_start: int = 512):
    """
    Parse assembled binary bitstring and load into CPU memory.
    
    The assembler outputs lines of binary bits (e.g. "0001010000110001").
    For CISC, multi-byte instructions span multiple lines.
    Each line is padded/aligned to the ISA's native word size.
    We convert each line to bytes and write sequentially to memory.
    """
    lines = binary_str.strip().split("\n")
    address = program_start
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Each line is a binary bitstring — convert to integer bytes
        # Pad to full byte boundary
        bit_len = len(line)
        padded = line.ljust(((bit_len + 7) // 8) * 8, '0')
        
        # Write byte by byte
        for i in range(0, len(padded), 8):
            byte_str = padded[i:i+8]
            byte_val = int(byte_str, 2)
            try:
                cpu.memory.write_data(address, byte_val, 1)
            except Exception:
                break
            address += 1
    
    # Set IP to program start
    cpu.set_pc(program_start)


def get_cpu_state(cpu: CPU) -> Dict[str, Any]:
    """Get full CPU state for the frontend."""
    if not cpu:
        return {}
    
    # Registers
    registers = dict(cpu.registers)
    
    # Flags
    flags = {
        "Z": cpu.get_flag("Z"),
        "C": cpu.get_flag("C"),
        "O": cpu.get_flag("O"),
        "N": cpu.get_flag("N"),
    }
    
    # Memory dump around IP and stack — provide key regions
    ip = cpu.get_pc()
    sp = cpu.registers.get("SP", 0)
    
    # Read memory around IP (program area)
    program_memory = []
    for addr in range(max(0, ip - 16), min(ip + 64, 65536)):
        try:
            val = cpu.memory.read_data(addr, 1)
            program_memory.append({"address": addr, "value": val})
        except Exception:
            break
    
    # Read memory from address 0 for a general dump
    memory_dump = []
    for addr in range(0, min(512, 65536)):
        try:
            val = cpu.memory.read_data(addr, 1)
            memory_dump.append(val)
        except Exception:
            memory_dump.append(0)
    
    # I/O output — check serial/port output
    output = ""
    if hasattr(cpu, 'output_buffer'):
        output = cpu.output_buffer
    
    return {
        "registers": registers,
        "flags": flags,
        "halted": cpu.halted,
        "ip": ip,
        "sp": sp,
        "memory": memory_dump,
        "output": output,
    }


@app.websocket("/api/simulate")
async def simulate_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    cpu = None
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            action = msg.get("action")
            
            if action == "init":
                config = msg.get("config", {})
                isa_name = config.get("isa", "risc3")
                isa = ISA(isa_name.lower())
                mem_arch = config.get("memory_architecture", "neumann")
                
                if mem_arch == "harvard":
                    mem = HarvardMemory()
                else:
                    mem = VonNeumannMemory()
                    
                io_sys = MemoryMappedIO(mem)
                cpu = CPU(isa, mem, io_sys)
                
                # Load binary into memory
                binary = config.get("binary", "")
                program_start = config.get("program_start", 512)
                if binary:
                    load_binary_to_memory(cpu, binary, program_start)
                
                await websocket.send_json({
                    "status": "initialized", 
                    "state": get_cpu_state(cpu)
                })
                
            elif action == "step":
                if cpu and not cpu.halted:
                    cpu.step()
                await websocket.send_json({
                    "status": "stepped", 
                    "state": get_cpu_state(cpu)
                })
                
            elif action == "run":
                max_cycles = msg.get("max_cycles", 1000)
                if cpu and not cpu.halted:
                    cpu.run(max_cycles)
                await websocket.send_json({
                    "status": "completed" if (cpu and cpu.halted) else "running",
                    "state": get_cpu_state(cpu)
                })
            
            elif action == "reset":
                if cpu:
                    # Re-initialize with same config
                    for reg_name in cpu.registers:
                        cpu.registers[reg_name] = 0
                    cpu.halted = False
                    if hasattr(cpu, 'output_buffer'):
                        cpu.output_buffer = ""
                    # Re-init special registers
                    if "SP" in cpu.registers:
                        cpu.registers["SP"] = cpu.memory.mem.size - 1 if hasattr(cpu.memory, 'mem') else 65535
                    if "BP" in cpu.registers:
                        cpu.registers["BP"] = cpu.registers.get("SP", 65535)
                    if "TOS" in cpu.registers:
                        cpu.registers["TOS"] = 256
                await websocket.send_json({
                    "status": "reset",
                    "state": get_cpu_state(cpu)
                })
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({
                "status": "error",
                "error": str(e),
                "state": get_cpu_state(cpu) if cpu else {}
            })
        except Exception:
            pass
