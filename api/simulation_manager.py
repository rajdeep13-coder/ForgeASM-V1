"""
ForgeASM Simulation Manager
============================
Provides a transport-independent simulation engine wrapper and an in-memory
session store so that each HTTP session has its own isolated CPU state.

Architecture:
    SimulationManager          (session registry – one per process)
        └── Simulation         (one per browser session / API client)
                └── CPU        (core engine – knows nothing about HTTP)
                └── Memory
                └── I/O

NOTE: The current session store is in-memory and therefore suitable for
single-instance development/demo deployment.  For a multi-instance production
deployment you would replace _sessions with a distributed cache (e.g. Redis),
but that is explicitly out of scope for ForgeASM V1.
"""
from __future__ import annotations

import uuid
import threading
from typing import Any, Dict, List, Optional, Tuple

from core.isa.isa_def import ISA
from core.isa.exceptions import InvalidISAError
from core.assembler.assembler import Assembler
from core.memory.memory import VonNeumannMemory, HarvardMemory
from core.io.io import MemoryMappedIO
from core.simulator.cpu import CPU
from api.models import SimulationState


# ─── Helper ───────────────────────────────────────────────────────────────────

def _load_binary_into_memory(cpu: CPU, binary_str: str, program_start: int = 0) -> None:
    """
    Parse the assembled binary (newline-separated bit strings) and write it
    byte-by-byte into CPU memory starting at *program_start*.

    For CISC, each logical instruction may produce multiple lines (opcode,
    register byte, optional immediate bytes) that are already byte-aligned.
    For RISC1/RISC2/RISC3, all bit strings are concatenated into one
    continuous bitstream and then sliced into bytes — this preserves the
    packed encoding that the CPU's bit-addressed fetch assumes.
    """
    isa_name = cpu.isa.name.lower()
    lines = [ln.strip() for ln in binary_str.strip().split("\n") if ln.strip()]

    if isa_name == "cisc":
        # CISC assembler emits one line per physical byte-group; each line is
        # already a multiple of 8 bits, so write line-by-line.
        address = program_start
        for line in lines:
            padded = line.ljust(((len(line) + 7) // 8) * 8, "0")
            for i in range(0, len(padded), 8):
                byte_val = int(padded[i : i + 8], 2)
                try:
                    if hasattr(cpu.memory, "instr_mem"):
                        cpu.memory.instr_mem.write_byte(address, byte_val)
                    else:
                        cpu.memory.write_data(address, byte_val, 1)
                except Exception:
                    break
                address += 1
    else:
        # RISC1/2/3: concatenate ALL bit lines into one stream, then write
        # bytes. This ensures that PC * isa_bit_size correctly indexes any
        # instruction in the packed stream.
        bit_stream = "".join(lines)
        # Pad to a full byte
        if len(bit_stream) % 8 != 0:
            bit_stream += "0" * (8 - len(bit_stream) % 8)

        address = program_start
        for i in range(0, len(bit_stream), 8):
            byte_val = int(bit_stream[i : i + 8], 2)
            try:
                if hasattr(cpu.memory, "instr_mem"):
                    cpu.memory.instr_mem.write_byte(address, byte_val)
                else:
                    cpu.memory.write_data(address, byte_val, 1)
            except Exception:
                break
            address += 1

    cpu.set_pc(program_start)


def _snapshot_memory(cpu: CPU, size: int = 512) -> List[int]:
    """Return up to *size* bytes from data memory as a list of ints."""
    result: List[int] = []
    for addr in range(size):
        try:
            result.append(cpu.memory.read_data(addr, 1))
        except Exception:
            result.append(0)
    return result


def _build_state_snapshot(sim: "Simulation") -> SimulationState:
    """Convert the live CPU state into a serialisable SimulationState."""
    cpu = sim.cpu

    # Build flags dynamically from the CPU's FR register so it works for all ISAs.
    # We read the four flags ForgeASM defines; any that aren't present default to False.
    flags: Dict[str, bool] = {
        "Z": cpu.get_flag("Z"),
        "C": cpu.get_flag("C"),
        "O": cpu.get_flag("O"),
        "N": cpu.get_flag("N"),
    }

    # Peek at the instruction currently sitting at PC (next to execute).
    current_instruction = sim._peek_instruction_name()

    return SimulationState(
        pc=cpu.get_pc(),
        registers=dict(cpu.registers),
        flags=flags,
        memory=_snapshot_memory(cpu),
        halted=cpu.halted,
        output=cpu.output_buffer,
        cycle_count=sim.cycle_count,
        current_instruction=current_instruction,
    )


# ─── Simulation ───────────────────────────────────────────────────────────────

class Simulation:
    """
    A single isolated simulation session.

    Wraps one CPU instance together with the configuration that created it so
    the session can be reset to its original state at any time.

    This class is completely transport-agnostic – it does not know about HTTP,
    WebSockets, or any other communication mechanism.
    """

    def __init__(
        self,
        simulation_id: str,
        isa_name: str,
        memory_architecture: str,
        binary: str,
        program_start: int,
    ) -> None:
        self.simulation_id = simulation_id
        self.isa_name = isa_name.lower()
        self.memory_architecture = memory_architecture.lower()
        self.binary = binary
        self.program_start = program_start
        self.cycle_count: int = 0

        # Build CPU for the first time
        self.cpu = self._build_cpu()
        _load_binary_into_memory(self.cpu, binary, program_start)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _build_cpu(self) -> CPU:
        """Construct a fresh CPU with memory and I/O subsystems."""
        isa = ISA(self.isa_name)

        if self.memory_architecture == "harvard":
            mem = HarvardMemory()
        else:
            mem = VonNeumannMemory()

        io_sys = MemoryMappedIO(mem)
        return CPU(isa, mem, io_sys)

    def reset(self) -> None:
        """Rebuild the CPU from scratch and reload the original binary."""
        self.cpu = self._build_cpu()
        _load_binary_into_memory(self.cpu, self.binary, self.program_start)
        self.cycle_count = 0

    # ── Operations ────────────────────────────────────────────────────────────

    def step(self) -> Optional[str]:
        """
        Execute exactly one instruction.

        Returns the name of the executed instruction (best-effort), or None if
        the CPU is already halted.
        """
        if self.cpu.halted:
            return None

        # Best-effort: peek at what instruction is about to execute
        last_name = self._peek_instruction_name()

        self.cpu.step()
        self.cycle_count += 1
        return last_name

    def run(self, max_cycles: int = 1000) -> Tuple[int, str]:
        """
        Execute up to *max_cycles* instructions.

        Returns ``(cycles_executed, halt_reason)`` where *halt_reason* is one of:
        - ``"halted"``       – CPU executed a HALT instruction
        - ``"max_cycles"``   – reached the cycle limit without halting
        - ``"already_halted"`` – CPU was already halted before run() was called
        """
        from core.memory.exceptions import MemoryError as MemErr

        if self.cpu.halted:
            return 0, "already_halted"

        cycles = 0
        try:
            while not self.cpu.halted and cycles < max_cycles:
                self.cpu.step()
                cycles += 1
        except MemErr:
            self.cpu.halted = True

        self.cycle_count += cycles

        halt_reason = "halted" if self.cpu.halted else "max_cycles"
        return cycles, halt_reason

    def get_state(self) -> SimulationState:
        """Return a complete snapshot of current CPU state."""
        return _build_state_snapshot(self)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _peek_instruction_name(self) -> Optional[str]:
        """
        Try to decode the opcode at the current PC without advancing it.
        Used to populate *last_instruction* in step responses.
        """
        try:
            cpu = self.cpu
            isa_name = self.isa_name
            opcode_len = {"risc1": 6, "risc2": 8, "risc3": 6, "cisc": 8}.get(isa_name, 8)
            isa_bit_size = {"risc1": 6, "risc2": 8, "risc3": 8, "cisc": 8}.get(isa_name, 8)
            bit_offset = cpu.get_pc() * isa_bit_size

            # Read enough bytes to get the opcode
            needed_bytes = (opcode_len + 7) // 8 + 1
            bits = ""
            byte_idx = bit_offset // 8
            for i in range(needed_bytes):
                b = cpu.memory.read_instr(byte_idx + i, 1)
                bits += f"{b:08b}"

            bit_rem = bit_offset % 8
            opcode_str = bits[bit_rem : bit_rem + opcode_len]
            inst = cpu.isa.get_instruction_by_opcode(opcode_str)
            return inst.name if inst else None
        except Exception:
            return None


# ─── SimulationManager ────────────────────────────────────────────────────────

class SimulationManager:
    """
    In-memory registry of active simulation sessions.

    Thread-safety: a simple threading.Lock guards the dict so that concurrent
    FastAPI requests on different event-loop threads cannot corrupt it.  For
    async routes running in a single-threaded event loop this lock is
    effectively a no-op, but it protects against any sync background threads.

    Scalability note: This store lives in the process heap.  A single Uvicorn
    worker (--workers 1) is sufficient for development and demo use.  For
    horizontal scaling you would persist sessions externally.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, Simulation] = {}
        self._lock = threading.Lock()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create(
        self,
        isa_name: str,
        memory_architecture: str,
        binary: str,
        program_start: int = 0,
    ) -> Simulation:
        """
        Create a new Simulation, store it, and return it.

        Raises ``InvalidISAError`` if *isa_name* is not recognised.
        """
        simulation_id = str(uuid.uuid4())
        sim = Simulation(
            simulation_id=simulation_id,
            isa_name=isa_name,
            memory_architecture=memory_architecture,
            binary=binary,
            program_start=program_start,
        )
        with self._lock:
            self._sessions[simulation_id] = sim
        return sim

    def get(self, simulation_id: str) -> Optional[Simulation]:
        """Return the Simulation for *simulation_id*, or None if not found."""
        with self._lock:
            return self._sessions.get(simulation_id)

    def delete(self, simulation_id: str) -> bool:
        """Remove a simulation.  Returns True if it existed, False otherwise."""
        with self._lock:
            if simulation_id in self._sessions:
                del self._sessions[simulation_id]
                return True
            return False

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)

    # ── Convenience (used by routes) ──────────────────────────────────────────

    def get_or_404(self, simulation_id: str) -> Simulation:
        """
        Return the Simulation or raise a SimulationNotFoundError.

        Route handlers catch SimulationNotFoundError and return HTTP 404.
        """
        sim = self.get(simulation_id)
        if sim is None:
            raise SimulationNotFoundError(simulation_id)
        return sim


# ─── Exceptions ───────────────────────────────────────────────────────────────

class SimulationNotFoundError(Exception):
    """Raised when a simulation_id does not exist in the manager."""

    def __init__(self, simulation_id: str) -> None:
        self.simulation_id = simulation_id
        super().__init__(f"Simulation '{simulation_id}' not found")


# ─── Module-level singleton ───────────────────────────────────────────────────
# FastAPI imports this directly in the route module; there is exactly one
# manager instance per process, which is the correct behaviour for V1.

simulation_manager = SimulationManager()
