"""
ForgeASM Assembler
==================
Two-pass assembler that converts assembly source text into binary bit strings.

Pass 1 — parse all instructions and compute the PC-unit address of every
         instruction (needed for correct jump-offset calculation).
Pass 2 — encode instructions using the PC-address table so that relative
         jump offsets are in the same units the CPU uses for its PC register.

The CPU tracks its program counter in *ISA word units* whose size varies:
    RISC1: 6 bits  → pc_inc is in 6-bit words
    RISC2: 8 bits  → pc_inc is in 8-bit words  (bytes)
    RISC3: 8 bits  → pc_inc is always 2 (fixed 16-bit instructions)
    CISC : 8 bits  → pc_inc varies (1 base + 1 for reg byte + 2 per imm word)

The assembler must encode jump offsets in these same PC units so that
    new_pc = current_pc + offset
lands exactly on the target instruction's PC address.
"""
from typing import List, Dict, Tuple
from core.isa.isa_def import ISA, InstructionDef
from core.assembler.parser import Parser, ParsedLine
from core.assembler.exceptions import AssemblerError


class Assembler:
    def __init__(self, isa: ISA):
        self.isa = isa
        self.parser = Parser()

        # Base instruction-word size in bits (= number of bits per PC unit)
        sizes = {"risc1": 6, "risc2": 8, "risc3": 8, "cisc": 8}
        self.instruction_size = sizes.get(isa.name.lower(), 8)

        self.jump_labels_allowed = {
            "jmp", "call", "je", "jne", "jl", "jle", "jg", "jge", "jc"
        }
        self.mov_labels_allowed = {
            "mov", "load", "store", "push", "mov_low", "mov_high",
            "cmp", "cmpe", "cmpb", "mul", "div"
        }

        # Populated during assemble(); maps instruction-line index → PC address
        self._pc_addr: List[int] = []

    # ─────────────────────────────────────────────────────────────────────────

    def assemble(self, text: str) -> str:
        self.parser = Parser()  # reset labels on each call
        parsed_lines = self.parser.parse(text)

        # ── Pass 1: compute PC address for every instruction ──────────────────
        self._build_pc_table(parsed_lines)

        # ── Pass 2: encode each instruction ───────────────────────────────────
        binary_lines: List[str] = []
        for idx, p_line in enumerate(parsed_lines):
            binary_line = self._assemble_line(p_line, idx)
            binary_lines.append(binary_line)

        return "\n".join(binary_lines)

    # ─── Pass-1 helpers ───────────────────────────────────────────────────────

    def _build_pc_table(self, parsed_lines: List[ParsedLine]) -> None:
        """Compute the PC-unit start address for every instruction line."""
        isa_name = self.isa.name.lower()
        self._pc_addr = []
        addr = 0
        for p_line in parsed_lines:
            self._pc_addr.append(addr)
            addr += self._instruction_pc_size(p_line, isa_name)

    def _instruction_pc_size(self, p_line: ParsedLine, isa_name: str) -> int:
        """
        Return the number of PC units consumed by a single instruction.

        For RISC1/RISC2 the base size is 1; instructions with an immediate
        operand add 2 (the immediate is 12 or 16 bits = 2 extra 6- or 8-bit
        words).  For RISC3 every instruction is 2 words (fixed 16-bit).
        For CISC, the size depends on the number of register and immediate
        operands encoded.
        """
        candidates = self.isa.get_instructions_by_name(p_line.instruction)
        if not candidates:
            return 1  # Unknown instruction — error will be raised in pass 2

        if isa_name == "risc3":
            return 2  # Always fixed 16-bit (2 × 8-bit words)

        # Pick the best-matching candidate — same logic as pass 2 encoding
        best = self._pick_best_candidate(p_line, candidates)
        if best is None:
            best = candidates[0]

        if isa_name in ("risc1", "risc2"):
            # Base = 1; add 2 if there is an immediate operand
            has_imm = any(t.startswith("imm") for t in best.operands)
            return 3 if has_imm else 1

        if isa_name == "cisc":
            # Derive size the same way decode_and_execute does at runtime:
            # look at the first 3 bits of the opcode to determine the format.
            op_bits = best.opcode[:3]
            cisc_styles = {
                "000": (1, 0), "001": (0, 0), "010": (0, 1), "011": (2, 0),
                "100": (1, 1), "101": (2, 1), "110": (1, 2),
            }
            reg_count, const_count = cisc_styles.get(op_bits, (0, 0))
            size = 1
            if reg_count > 0:
                size += 1            # 1 byte for the combined register field
            size += const_count * 2  # 2 bytes per immediate constant
            return size

        return 1  # fallback

    def _pick_best_candidate(
        self, p_line: ParsedLine, candidates: List[InstructionDef]
    ) -> "InstructionDef | None":
        """
        Choose the instruction variant that best matches the source operands.

        Strategy (in priority order):
        1. Exact operand-count match where each operand type is compatible
           (e.g. an operand starting with '$' or a digit is an immediate, a
           '%'-prefixed token or bare register name is a register).
        2. Simple operand-count match as a fallback.
        """
        op_count = len(p_line.operands)

        def _classify(token: str) -> str:
            """Return 'reg' or 'imm' for a source token."""
            t = token.strip().lstrip("$").strip()
            # Immediate: starts with digit, minus, $, or is a label ref
            if token.startswith("$") or token.startswith("."):
                return "imm"
            # Try register lookup
            clean = token.replace("[", "").replace("]", "").replace("%", "").strip()
            if self.isa.get_register(clean):
                return "reg"
            # Memory-indirect register: [REG]
            if token.startswith("["):
                return "memreg"
            # Default — treat as immediate
            return "imm"

        src_types = [_classify(op) for op in p_line.operands]

        def _compat(op_type: str, src: str) -> bool:
            if op_type.startswith("imm"):
                return src == "imm"
            if op_type in ("reg",):
                return src == "reg"
            if op_type in ("memreg",):
                return src in ("reg", "memreg")
            if op_type in ("regoff", "memregoff"):
                return True  # complex token, skip strict check
            return True

        # Pass 1: full type-compatible match
        for cand in candidates:
            op_types = [t for t in cand.operands if t != "one"]
            if len(op_types) != op_count:
                continue
            if all(_compat(ot, st) for ot, st in zip(op_types, src_types)):
                return cand

        # Pass 2: count-only match
        for cand in candidates:
            op_types = [t for t in cand.operands if t != "one"]
            if len(op_types) == op_count:
                return cand

        return None

    # ─── Pass-2 encoding ──────────────────────────────────────────────────────

    def _assemble_line(self, p_line: ParsedLine, instr_index: int) -> str:
        candidates = self.isa.get_instructions_by_name(p_line.instruction)
        if not candidates:
            raise AssemblerError(
                f"Unknown instruction: {p_line.instruction}",
                p_line.line_number, p_line.original_text,
            )

        last_error = None
        for candidate in candidates:
            try:
                return self._encode_instruction(p_line, candidate, instr_index)
            except AssemblerError as e:
                last_error = e

        raise last_error or AssemblerError(
            "No matching operand signature found",
            p_line.line_number, p_line.original_text,
        )

    def _encode_instruction(
        self, p_line: ParsedLine, inst_def: InstructionDef, instr_index: int
    ) -> str:
        op_types = [t for t in inst_def.operands if t != "one"]

        if len(p_line.operands) != len(op_types):
            raise AssemblerError(
                f"Expected {len(op_types)} operands, got {len(p_line.operands)}",
                p_line.line_number, p_line.original_text,
            )

        opcode = inst_def.opcode
        # 5-bit opcode special case
        if p_line.instruction in ("mov_low", "mov_high") and len(opcode) > 5:
            opcode = opcode[:5]

        binary_part = opcode
        cisc_reg_byte = ""
        imm_bytes = ""

        for operand, op_type in zip(p_line.operands, op_types):
            encoded_parts = self._encode_operand(
                operand, op_type, p_line.instruction, instr_index, p_line
            )
            for encoded_op, loc in encoded_parts:
                if loc == "reg":
                    if self.isa.name == "cisc":
                        cisc_reg_byte += encoded_op
                    else:
                        binary_part += encoded_op
                elif loc == "imm":
                    if self.isa.name == "cisc":
                        imm_bytes += encoded_op
                    else:
                        binary_part += encoded_op

        if self.isa.name == "cisc":
            # Only include the register byte line if there are register operands.
            # For instructions with 0 register operands (e.g. push $imm, jmp $off),
            # the CPU's cisc_styles table does not read a register byte, so we must
            # not write one — otherwise the immediate would be read from the wrong offset.
            if cisc_reg_byte:
                cisc_reg_byte = cisc_reg_byte.ljust(8, "0")
                return binary_part + "\n" + cisc_reg_byte + (
                    "\n" + imm_bytes if imm_bytes else ""
                )
            else:
                return binary_part + ("\n" + imm_bytes if imm_bytes else "")

        # RISC3: fixed 16-bit instruction words — pad to 16 bits
        if self.isa.name.lower() == "risc3":
            return binary_part.ljust(16, "0")

        return binary_part

    def _encode_operand(
        self,
        operand: str,
        op_type: str,
        instr_name: str,
        instr_index: int,
        p_line: ParsedLine,
    ):
        """Return list of (encoded_bits, destination_type) pairs."""

        if op_type in ("reg", "fr", "memreg", "simdreg"):
            clean_op = operand.replace("[", "").replace("]", "").replace("%", "").strip()
            reg = self.isa.get_register(clean_op)
            if not reg and (clean_op.startswith("R") or clean_op.startswith("r")):
                reg = self.isa.get_register(clean_op)
            if not reg:
                raise AssemblerError(
                    f"Invalid register: {operand}",
                    p_line.line_number, p_line.original_text,
                )
            return [(reg.encoding, "reg")]

        elif op_type in ("regoff", "memregoff"):
            clean = (
                operand.replace("[", "").replace("]", "")
                       .replace("%", "").replace(" ", "")
            )
            sign = 1
            idx = clean.find("+")
            if idx == -1:
                idx = clean.find("-")
                sign = -1
            if idx == -1:
                raise AssemblerError(
                    f"Expected offset in {operand}",
                    p_line.line_number, p_line.original_text,
                )
            reg_name = clean[:idx]
            off_str = clean[idx + 1:]
            reg = self.isa.get_register(reg_name)
            if not reg:
                raise AssemblerError(
                    f"Invalid register: {reg_name}",
                    p_line.line_number, p_line.original_text,
                )
            try:
                if off_str.startswith("$"):
                    off_str = off_str[1:]
                offset = int(off_str, 0) * sign
            except ValueError:
                raise AssemblerError(
                    f"Invalid offset: {off_str}",
                    p_line.line_number, p_line.original_text,
                )
            imm_bits = self._encode_number(offset, 16, p_line)
            return [(reg.encoding, "reg"), (imm_bits, "imm")]

        elif op_type.startswith("imm"):
            val_str = operand
            if val_str.startswith("$"):
                val_str = val_str[1:]

            val = 0
            if val_str.startswith("."):
                label = val_str[1:]
                if instr_name in self.jump_labels_allowed and label in self.parser.jump_labels:
                    target_idx = self.parser.jump_labels[label]
                    # Compute offset in PC units (not raw instruction-line units)
                    target_pc = self._pc_addr[target_idx] if target_idx < len(self._pc_addr) else target_idx
                    source_pc = self._pc_addr[instr_index] if instr_index < len(self._pc_addr) else instr_index
                    val = target_pc - source_pc
                elif instr_name in self.mov_labels_allowed and label in self.parser.mov_labels:
                    label_val = self.parser.mov_labels[label]
                    val = label_val[0] if isinstance(label_val, list) else label_val
                else:
                    raise AssemblerError(
                        f"Unknown or invalid label usage: {label}",
                        p_line.line_number, p_line.original_text,
                    )
            else:
                try:
                    val = int(val_str, 0)
                except ValueError:
                    raise AssemblerError(
                        f"Invalid immediate: {val_str}",
                        p_line.line_number, p_line.original_text,
                    )
                # For RISC3, raw literal jump offsets are in instruction units.
                # Scale by 2 to convert to PC-unit (byte) offsets since RISC3
                # instructions are always 2 bytes (16 bits) long.
                isa_name_check = self.isa.name.lower()
                if isa_name_check == "risc3" and instr_name in self.jump_labels_allowed:
                    val *= 2

            isa_name = self.isa.name.lower()
            if isa_name == "risc3" and len(op_type) > 3:
                bit_len = int(op_type[3:])
            elif isa_name == "risc3":
                bit_len = 16
            elif isa_name == "risc1":
                bit_len = 12
            elif isa_name == "risc2":
                bit_len = 16
            else:
                bit_len = 16  # cisc default

            return [(self._encode_number(val, bit_len, p_line), "imm")]

        raise AssemblerError(
            f"Unsupported operand type: {op_type}",
            p_line.line_number, p_line.original_text,
        )

    def _encode_number(self, num: int, bit_len: int, p_line: ParsedLine) -> str:
        min_val = -(2 ** (bit_len - 1))
        if not (min_val <= num < (2 ** bit_len)):
            raise AssemblerError(
                f"Immediate {num} out of bounds for {bit_len} bits",
                p_line.line_number, p_line.original_text,
            )
        if num < 0:
            num = (1 << bit_len) + num
        return format(num, f"0{bit_len}b")
