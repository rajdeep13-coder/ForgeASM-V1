# ISA translation

Translation is verified by the simulator, not by the model. A translation
episode has a source ISA, a target ISA, source assembly, and one or more
test vectors. Each vector supplies the initial registers/memory, memory
architecture, and cycle cap.

## Observables

Observables are ISA-neutral values declared by the task:

- `memory_ranges`: half-open byte ranges such as `[20, 24]`. The verifier
  compares the bytes at those addresses.
- `output`: the simulator's designated output device text. This is not a
  register and is available across the ISAs through their `OUT` instruction.
- `halted`: whether execution reached a halt instruction before the vector's
  cycle cap.

Registers, flags, program counters, and internal stack layouts are never
translation observables. They may differ legitimately between ISAs.

For every vector, ForgeASM runs both programs with strict simulation enabled.
Assembly errors, strict opcode errors, timeouts, or observable differences
make that vector fail. Feedback sent to the model contains only the vector ID,
the differing observable names, and their source/target values; checker code
and task internals are not exposed.

Translation episodes use the same bounded repair and JSONL persistence
conventions as solve episodes. The instruction-count ratio is target
instructions divided by source instructions, excluding blank and comment
lines.
