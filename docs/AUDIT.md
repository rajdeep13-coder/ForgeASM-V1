# ForgeASM Ground-Truth Audit

This document describes the active implementation in `core/` and `api/`, not
the older experimental implementation in `modules/` or the Flask site in
`website/`. The source of truth for instruction encodings is
`core/isa/instructions.json`; register metadata is in
`core/isa/registers.json`.

## ISA definition format

`registers.json` is an object keyed by ISA name. Each register entry is:

```json
["NAME", general_purpose_boolean, "ENCODING_BITS", "description"]
```

`instructions.json` is an object keyed by ISA name. Each opcode entry is:

```json
"opcode_bits": ["mnemonic", result_destination_or_list, ["operand_type", ...]]
```

The second field is metadata consumed by the assembler/ISA loader and by
documentation; execution dispatches on the mnemonic. `one` is an implicit
operand and is not written in source. `immN` is an N-bit immediate. `imm` is a
16-bit immediate for CISC. `reg` is a register encoding, `memreg` is an
indirect register memory operand, and `memregoff` is an indirect register plus
signed 16-bit offset. RISC-1 and RISC-2 use an opcode high bit to select an
immediate form; their immediate widths are 12 and 16 bits respectively.

### Registers

| ISA | Registers |
|---|---|
| RISC-1 | `FR`, `SP`, `IP`, `TOS` |
| RISC-2 | `FR`, `SP`, `IP`, `IR`, `ACC` |
| RISC-3 | `SP`, `IP`, `LR`, `FR`, `R00`, `R01`, `R02`, `R03` |
| CISC | `R00`, `R01`, `R02`, `R03`, `SP`, `BP`, `FR`, `IP` |

All register values are stored as 16-bit values. RISC-1 initializes `TOS` to
256. `SP` initializes to the last byte of the memory bank (65535 for
Von Neumann memory); CISC initializes `BP` from `SP`.

### Exact mnemonics and operand forms

The following lists are grouped by mnemonic. Duplicate opcode entries are
variants of the same source mnemonic.

**RISC-1 (6-bit base opcode):**

| Mnemonics | Operand forms |
|---|---|
| `halt`, `load`, `loadf`, `store`, `storef`, `swap`, `dup`, `dup2`, `push`, `pushf`, `pop`, `popf`, `add`, `sub`, `mul`, `div`, `and`, `or`, `xor`, `not`, `ret`, `nop` | no source operand |
| `mov`, `lsh`, `rsh`, `cmpe`, `cmpb`, `jmp`, `jc`, `call`, `in`, `out` | one immediate (`imm`); `call` and `jmp`/`jc` also have stack forms where defined |
| `call` | immediate or stack target |
| `cmpe`, `cmpb` | register-stack form or immediate |
| `jmp`, `jc` | immediate or stack offset |

RISC-1 is stack based. `mov` pushes an immediate, arithmetic consumes the top
two values and pushes the result, and `out` consumes the top value.

**RISC-2 (8-bit base opcode):**

| Mnemonics | Operand forms |
|---|---|
| `halt`, `load`, `loadf`, `loadi`, `store`, `storef`, `storei`, `push`, `pushf`, `pushi`, `pop`, `popf`, `popi`, `add`, `sub`, `inc`, `dec`, `mul`, `div`, `and`, `or`, `xor`, `not`, `ret`, `nop` | no source operand |
| `store`, `mov`, `lsh`, `rsh`, `call`, `cmp`, `test`, `jmp`, `je`, `jne`, `jg`, `jge`, `jl`, `jle`, `in`, `out` | one immediate where the JSON provides an immediate variant |
| `call` | accumulator target or immediate offset |
| `cmp`, `test` | memory-at-`IR` or immediate |
| conditional branches | accumulator target or immediate offset, according to the JSON variant |

RISC-2 is accumulator based: arithmetic operates on `ACC`; `IR` supplies
indirect memory addresses; `push*` and `pop*` use the hardware stack.

**RISC-3 (fixed 16-bit instruction words, 8-bit PC units):**

`halt`, `ret`, and `nop` have no operands. The remaining forms are:

| Mnemonics | Operand forms |
|---|---|
| `load` | `reg, memreg` |
| `store` | `memreg, reg` |
| `mov` | `reg, reg` |
| `mov_low`, `mov_high` | `reg, imm8` |
| `push`, `pop` | `reg` |
| `add`, `sub`, `mul`, `div`, `and`, `or`, `xor`, `lsh`, `rsh` | `reg, reg, reg` |
| `addc` | `reg, reg` |
| `not` | `reg, reg` |
| `call` | `imm10` or `reg` |
| `cmp` | `reg, reg` or `reg, imm7` |
| `test` | `reg, reg` |
| `jmp` | `imm10` or `reg` |
| `je`, `jne`, `jg`, `jge`, `jl`, `jle` | `imm10` |
| `in` | `reg, imm7` |
| `out` | `imm5, imm5` or `imm7, reg` |

**CISC (8-bit opcode, variable length):**

`halt`, `leave`, `ret`, and `nop` have no operands. CISC supports the
following forms:

| Mnemonics | Operand forms |
|---|---|
| `mov` | `reg, imm`; `reg, reg`; `reg, memreg`; `reg, memregoff`; `memreg, reg`; `memreg, imm`; `memregoff, reg`; `memregoff, imm` |
| `push` | `reg` or `imm`; `pop` is `reg` |
| `enter` | `imm` |
| `add`, `sub` | `reg, memreg`; `reg, reg`; `reg, memregoff`; `memreg, reg` |
| `inc`, `dec` | `reg, one`; `memreg, one`; `memregoff, one` |
| `mul`, `div` | `reg, reg`; `reg, memreg`; `memreg, reg`; `reg, imm`; `reg, memregoff` |
| `and`, `or`, `xor` | `reg, reg` or `reg, memreg` |
| `not` | `reg` or `memreg` |
| `lsh`, `rsh` | `reg, imm`; `memreg, imm`; `memregoff, imm` |
| `call` | `imm`, `reg`, or `regoff` |
| `cmp`, `test` | register, memory-register, immediate, or offset variants as defined in JSON |
| `jmp` | `imm`, `reg`, or `regoff` |
| `je`, `jne`, `jg`, `jge`, `jl`, `jle` | `imm` |
| `in` | `reg, imm`; `memreg, imm`; `memregoff, imm` |
| `out` | `imm, reg`; `imm, memreg`; `imm, memregoff` |
| `load4`, `store4` | `simdreg` |
| `add4`, `sub4`, `mul4`, `div4` | `simdreg, reg` |

The six `*4` CISC forms are defined in the JSON but are not implemented by
the CPU. Strict mode reports them instead of silently doing nothing.

## Flags, memory, branching, halting, and I/O

`FR` uses bit 12 for carry (`C`), bit 13 for zero (`Z`), bit 14 for overflow
(`O`), and bit 15 for sign/negative (`S`/`N`). Arithmetic and comparisons call
the common `_update_flags` helper. Loads, stores, moves, branches, stack
operations, and shifts do not generally update flags. Branch conditions use
`Z`, `S`, and `O`; `jc` in RISC-1 uses `Z` as implemented by its comparison
semantics.

`VonNeumannMemory` has one 65536-byte bank for instruction and data access.
`HarvardMemory` has separate 32768-byte instruction and data banks. Words are
big-endian. The API's memory snapshot exposes the first 512 data bytes.

`halt` sets `CPU.halted`. A normal simulation stops when this flag becomes
true. `Simulation.run(max_cycles)` also stops after the requested instruction
count and returns `max_cycles` without setting `CPU.halted`; the API state
model's historical description says “halted or exceeded cycles”, but the
implementation distinguishes these cases through `halt_reason`. Input
instructions set `is_input_active`; subsequent CPU steps return without
executing until input is supplied, and the current API has no input endpoint.

Load/store support exists in all four ISAs. Conditional branches exist in
RISC-2, RISC-3, and CISC; RISC-1 exposes `jc` and unconditional `jmp` but not
the RISC-2/RISC-3/CISC condition set. Calls and returns exist in all four.
I/O mnemonics `in` and `out` exist in all four, but input is a waiting flag and
output appends printable ASCII (1 through 127) to `output_buffer`.

## Assembler pipeline and errors

`Assembler.assemble` resets a `Parser`, parses source, builds a PC-address
table, then encodes each parsed instruction. The first pass accounts for
immediate widths, fixed RISC-3 words, and CISC register/immediate byte groups.
The second pass chooses an operand-compatible instruction variant and encodes
it. Labels are relative for jumps/calls and data labels are used by the
assembler's permitted move/load/store-style instructions.

`Parser` ignores blank lines and `#` comments, splits operands on commas, and
uses dot-prefixed directives for labels/data. Errors retain the old human
string (`str(error)` includes `Line N:` and the original line when available)
and now expose:

```python
error.as_dict()
# {kind, line, column, token, message, hint}
```

`kind` is one of `unknown_mnemonic`, `bad_operand`, `undefined_label`,
`duplicate_label`, `range_error`, or `invalid_directive`. The legacy error
messages are not replaced. Before this change, errors were unstructured
`AssemblerError` strings with an optional line number and full line text; they
did not reliably expose a column, token, kind, or hint.

## Simulator and in-process execution

The transport-independent path is:

```python
from api.simulation_manager import simulation_manager
sim = simulation_manager.create("risc3", "neumann", binary, strict=False)
sim.step()
cycles, reason = sim.run(max_cycles=1000)
state = sim.get_state()
simulation_manager.delete(sim.simulation_id)
```

`state` contains `pc`, all `registers`, dynamic `flags`, the first 512 data
memory bytes, `halted`, captured `output`, `cycle_count`, and the next
instruction name when it can be decoded. The manager is an in-memory,
thread-locked registry and is intended for a single process.

For agent/evaluation code, `core.runtime.run_program` assembles and runs
without HTTP:

```python
run_program(
    isa="risc3",
    memory_arch="neumann",
    source="mov_low R00, 1\nhalt",
    init={"registers": {"R00": 0}, "memory": {32: 7}},
    max_cycles=1000,
    strict=True,
    memory_ranges=[(0, 64)],
    trace=True,
)
```

The result contains `assembled`, structured `errors`, `halted`, `timed_out`,
`cycles`, `registers`, `flags`, `memory_dump`, and an optional capped trace of
state diffs. `strict=True` is the safe default for this helper and is enabled
for the Copilot; the public simulation API remains non-strict for compatibility.

## Strict execution and silent behavior audit

`CPU` now raises `SimulationError` in strict mode with:
`kind`, `cycle`, `pc`, `opcode`, and `message`.

* An opcode absent from `ISA.instructions` is `unknown_opcode`.
* A JSON-defined mnemonic absent from the CPU implementation is
  `unimplemented_opcode`; currently this includes CISC `load4`, `store4`,
  `add4`, `sub4`, `mul4`, and `div4`.
* Strict mode is passed through `SimulationManager.create(..., strict=True)`.
  The default remains `False`, so existing callers preserve the old behavior.

Known silent or compatibility behaviors found in the code:

1. In non-strict mode, an unknown opcode sets `halted=True` and returns without
   a structured error.
2. `_read_bits` catches memory read exceptions and substitutes zero bytes,
   which can turn an out-of-range fetch into a decoded zero pattern.
3. `_peek_instruction_name` catches all exceptions and returns `None`; this is
   presentation-only but hides decode failures from API state.
4. `Simulation.run` catches memory errors and turns them into a halted CPU
   rather than exposing the memory exception.
5. `_load_binary_into_memory` catches all write exceptions and breaks, allowing
   a partially loaded program.
6. The explicit `nop` branches use `pass` intentionally.
7. RISC-2/RISC-3/CISC handlers have operand-count guards that advance the PC
   or simply skip the operation for malformed decoded operands. The assembler
   normally prevents these forms, but corrupted binary can reach them.
8. Division by zero returns zero in the arithmetic handlers rather than
   raising an execution error.
9. `CPU.fetch()` is an empty compatibility method and returns an empty
   `bytearray`; execution uses `decode_and_execute` instead.
10. `ModifiedHarvardMemory` is an intentional empty subclass of
    `VonNeumannMemory`.

Strict mode addresses the two agent-critical opcode cases without changing
these legacy defaults. Memory faults, malformed decoded operands, division by
zero, input waiting, and partial loading remain documented compatibility
behaviors and are candidates for a future separately gated strict policy.

## Test and CI surface

The maintained suite lives under `tests/` and is selected by `pytest.ini`.
Legacy root/module/website files include scripts with import-time execution,
Windows-incompatible `curses`, or assumptions about an already-running HTTP
server, so they were not moved automatically. GitHub Actions runs the
maintained suite on pushes and pull requests.

## ModelGateway boundary

All model traffic is centralized in `copilot.ModelGateway`. Its
`generate(messages, images=None, tools=None, json_schema=None, tier="fast")`
method returns text, normalized tool calls, token usage, latency, model/backend
identity, and `bytes_off_device`. `GEMMA_BACKEND` selects `LOCAL` (the default,
OpenAI-compatible endpoint) or optional `CLOUD`; `GEMMA_FAST_MODEL` is required
for the selected backend and `GEMMA_HEAVY_MODEL` is used for `tier="heavy"`.

At FastAPI startup the gateway lists installed models and runs tiny text,
image, tool, and JSON-schema probes. Probe results are available from
`GET /api/copilot/capabilities`. If native tool calling is unavailable, the
gateway requests and validates the text protocol
`{"tool": "...", "args": {...}}` against the same tool schema. Calls are
retried once with backoff. `GET /api/copilot/telemetry` exposes in-memory
records; each record is also appended to
`COPILOT_TELEMETRY_PATH` (default `logs/copilot_telemetry.jsonl`). Local calls
always report `bytes_off_device: 0`. The Copilot run route uses the optional
`X-Session-ID` request header and records it with each JSONL telemetry entry.
