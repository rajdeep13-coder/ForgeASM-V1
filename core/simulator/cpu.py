import logging
from typing import Dict, Any, Optional
from core.isa.isa_def import ISA, InstructionDef, RegisterDef
from core.memory.memory import MemorySystem
from core.io.io import IOSystem

logger = logging.getLogger(__name__)


def twos_complement(val: int, bits: int) -> int:
    """Convert an unsigned bit-pattern to a signed Python int."""
    if val < 0:
        val = (1 << bits) + val
    else:
        if (val & (1 << (bits - 1))) != 0:
            val = val - (1 << bits)
    return val


class CPU:
    def __init__(self, isa: ISA, memory: MemorySystem, io_sys: IOSystem):
        self.isa = isa
        self.memory = memory
        self.io = io_sys

        # Initialise all registers to 0
        self.registers: Dict[str, int] = {}
        for reg in self.isa.registers.values():
            self.registers[reg.name.upper()] = 0

        self.halted = False
        self.is_input_active = False
        self.input_result_destination = None
        self.output_buffer = ""

        # Default special-register initialisation
        if "SP" in self.registers:
            mem = getattr(self.memory, 'mem', None)
            self.registers["SP"] = (getattr(mem, 'size', 65536) - 1) if mem else 65535
        if "BP" in self.registers:
            self.registers["BP"] = self.registers.get("SP", 65535)
        if "TOS" in self.registers:
            self.registers["TOS"] = 256  # RISC1 stack starts at byte 256

        self.isa_bit_size = {"risc1": 6, "risc2": 8, "risc3": 8, "cisc": 8}.get(
            self.isa.name.lower(), 8
        )

    # ─── PC helpers ───────────────────────────────────────────────────────────

    def get_pc(self) -> int:
        return self.registers.get("IP", 0)

    def set_pc(self, val: int):
        self.registers["IP"] = val & 0xFFFF

    # ─── Flag helpers ─────────────────────────────────────────────────────────
    # FR layout: bit12=C, bit13=Z, bit14=O, bit15=S/N

    def get_flag(self, flag: str) -> bool:
        fr = self.registers.get("FR", 0)
        bit = {"C": 12, "Z": 13, "O": 14, "S": 15, "N": 15}.get(flag.upper(), -1)
        if bit != -1:
            return bool((fr >> bit) & 1)
        return False

    def set_flag(self, flag: str, val: bool):
        if "FR" not in self.registers:
            return
        fr = self.registers["FR"]
        bit = {"C": 12, "Z": 13, "O": 14, "S": 15, "N": 15}.get(flag.upper(), -1)
        if bit != -1:
            if val:
                fr |= (1 << bit)
            else:
                fr &= ~(1 << bit)
            self.registers["FR"] = fr

    def _update_flags(self, res_val: int, op1: int, op2: int, bits: int, is_sub: bool = False):
        if "FR" not in self.registers:
            return
        cf = 1 if (res_val >> bits) & 1 else 0
        res_clean = res_val & ((1 << bits) - 1)
        zf = 1 if res_clean == 0 else 0
        sf = (res_clean >> (bits - 1)) & 1

        sign1 = (op1 >> (bits - 1)) & 1
        sign2 = (op2 >> (bits - 1)) & 1
        sign_res = sf
        if is_sub:
            of = 1 if (sign1 != sign2) and (sign1 != sign_res) else 0
        else:
            of = 1 if (sign1 == sign2) and (sign1 != sign_res) else 0

        # Clear bits 12-15, then set them
        fr = self.registers["FR"] & 0x0FFF
        if cf:
            fr |= (1 << 12)
        if zf:
            fr |= (1 << 13)
        if of:
            fr |= (1 << 14)
        if sf:
            fr |= (1 << 15)
        self.registers["FR"] = fr

    # ─── State snapshot ───────────────────────────────────────────────────────

    def get_state(self) -> Dict[str, Any]:
        return {
            "registers": self.registers.copy(),
            "halted": self.halted,
            "is_input_active": self.is_input_active,
            "output": self.output_buffer,
        }

    # ─── Memory loading ───────────────────────────────────────────────────────

    def load_binary(self, binary_str: str):
        bits = binary_str.replace('\n', '').replace(' ', '')
        if len(bits) % 8 != 0:
            bits += '0' * (8 - len(bits) % 8)

        bit_offset = self.get_pc() * self.isa_bit_size
        byte_start = bit_offset // 8
        for i in range(0, len(bits), 8):
            val = int(bits[i:i + 8], 2)
            if hasattr(self.memory, 'instr_mem'):
                self.memory._write(self.memory.instr_mem, byte_start + (i // 8), val, 1)
            else:
                self.memory.write_data(byte_start + (i // 8), val, 1)

    # ─── Bit-level instruction reading ───────────────────────────────────────

    def _read_bits(self, bit_offset: int, num_bits: int) -> str:
        byte_idx = bit_offset // 8
        bit_rem = bit_offset % 8
        needed_bytes = (bit_rem + num_bits + 7) // 8

        bit_str = ""
        for i in range(needed_bytes):
            try:
                b = self.memory.read_instr(byte_idx + i, 1)
                bit_str += f"{b:08b}"
            except Exception:
                bit_str += "00000000"

        return bit_str[bit_rem:bit_rem + num_bits]

    # ─── RISC1 stack helpers ──────────────────────────────────────────────────

    def _r1_pop(self) -> int:
        """Pop the top value from the RISC1 stack and return it."""
        tos = self.registers.get("TOS", 256)
        val = self.memory.read_data(tos - 2, 2)
        self.registers["TOS"] = tos - 2
        return val & 0xFFFF

    def _r1_push(self, val: int):
        """Push a 16-bit value onto the RISC1 stack."""
        tos = self.registers.get("TOS", 256)
        self.memory.write_data(tos, val & 0xFFFF, 2)
        self.registers["TOS"] = tos + 2

    def _r1_peek(self) -> int:
        """Return the top value without removing it."""
        tos = self.registers.get("TOS", 256)
        return self.memory.read_data(tos - 2, 2) & 0xFFFF

    # ─── RISC1 execute ────────────────────────────────────────────────────────

    def _execute_risc1(self, inst_def: InstructionDef, args: list, pc: int, pc_inc: int):
        """Execute one RISC1 (stack-based) instruction."""
        name = inst_def.name
        new_pc = pc + pc_inc

        if name == "halt":
            self.halted = True
            return

        elif name == "nop":
            pass

        elif name == "mov":
            # Push immediate onto stack
            if args:
                self._r1_push(args[0] & 0xFFFF)

        elif name in ["add", "sub", "mul", "div", "and", "or", "xor"]:
            b = self._r1_pop()
            a = self._r1_pop()
            if name == "add":
                res = a + b
            elif name == "sub":
                res = a - b
            elif name == "mul":
                res = a * b
            elif name == "div":
                res = (a // b) if b != 0 else 0
            elif name == "and":
                res = a & b
            elif name == "or":
                res = a | b
            elif name == "xor":
                res = a ^ b
            else:
                res = 0
            self._update_flags(res, a, b, 16, is_sub=(name == "sub"))
            self._r1_push(res & 0xFFFF)

        elif name == "not":
            a = self._r1_pop()
            res = (~a) & 0xFFFF
            self._r1_push(res)

        elif name == "lsh":
            # args[0] is the immediate shift count
            a = self._r1_pop()
            shift = args[0] if args else 0
            res = (a << shift) & 0xFFFF
            self._r1_push(res)

        elif name == "rsh":
            a = self._r1_pop()
            shift = args[0] if args else 0
            res = (a >> shift) & 0xFFFF
            self._r1_push(res)

        elif name == "inc":
            a = self._r1_pop()
            res = (a + 1) & 0xFFFF
            self._update_flags(a + 1, a, 1, 16)
            self._r1_push(res)

        elif name == "dec":
            a = self._r1_pop()
            res = (a - 1) & 0xFFFF
            self._update_flags(a - 1, a, 1, 16, is_sub=True)
            self._r1_push(res)

        elif name == "dup":
            val = self._r1_peek()
            self._r1_push(val)

        elif name == "dup2":
            # Push second-from-top
            tos = self.registers.get("TOS", 256)
            val = self.memory.read_data(tos - 4, 2) & 0xFFFF
            self._r1_push(val)

        elif name == "swap":
            b = self._r1_pop()
            a = self._r1_pop()
            self._r1_push(b)
            self._r1_push(a)

        elif name == "cmpe":
            # result_dest ["tos", "tospop", "imm"]  → pop TOS, compare with imm, set flags.
            # result_dest ["tos", "tospop", "tospop"] → pop two values, compare.
            # In both cases the comparison value is consumed (tospop).
            if args:
                # immediate variant: POP TOS, compare with immediate, set flags
                a = self._r1_pop()
                imm = args[0] & 0xFFFF
                self._update_flags(a - imm, a, imm, 16, is_sub=True)
            else:
                b = self._r1_pop()
                a = self._r1_pop()
                self._update_flags(a - b, a, b, 16, is_sub=True)

        elif name == "cmpb":
            # Same semantics as cmpe: pop TOS (or two values), set flags
            if args:
                a = self._r1_pop()
                imm = args[0] & 0xFFFF
                self._update_flags(a - imm, a, imm, 16, is_sub=True)
            else:
                b = self._r1_pop()
                a = self._r1_pop()
                self._update_flags(a - b, a, b, 16, is_sub=True)

        elif name == "cmp":
            if args:
                a = self._r1_pop()
                imm = args[0] & 0xFFFF
                self._update_flags(a - imm, a, imm, 16, is_sub=True)
            else:
                b = self._r1_pop()
                a = self._r1_pop()
                self._update_flags(a - b, a, b, 16, is_sub=True)

        elif name == "out":
            # Opcode 101011: operands = ["imm", "tospop"]
            # args[0] = port number (immediate), data comes from TOS
            val = self._r1_pop()
            char_val = val & 0xFF
            if 0 < char_val < 128:
                self.output_buffer += chr(char_val)

        elif name == "in":
            # Push from I/O port — mark as waiting for input
            self.is_input_active = True

        elif name in ["jmp", "je", "jne", "jg", "jge", "jl", "jle", "jc"]:
            # args[-1] is the signed offset (immediate)
            # For the TOS-variant (no imm), the offset is on the stack
            if args:
                dist = args[-1]
            else:
                dist = twos_complement(self._r1_pop(), 16)

            cond = False
            z = self.get_flag("Z")
            s = self.get_flag("S")
            o = self.get_flag("O")
            c = self.get_flag("C")

            if name == "jmp":
                cond = True
            elif name == "je":
                cond = z
            elif name == "jne":
                cond = not z
            elif name == "jg":
                cond = (s == o) and not z
            elif name == "jge":
                cond = (s == o)
            elif name == "jl":
                cond = (s != o)
            elif name == "jle":
                cond = (s != o) or z
            elif name == "jc":
                # "jc" = "jump if condition" — in RISC1, the condition is set by
                # cmpe/cmpb which set Z=1 when the two operands are equal.
                # Jump when Z=1 (the comparison was equal / end-of-sequence).
                cond = z

            if cond:
                new_pc = pc + dist

        elif name == "call":
            if args:
                dist = args[0]
                self._r1_push(new_pc & 0xFFFF)
                new_pc = pc + dist
            else:
                # TOS variant: address is on stack
                target = self._r1_pop()
                self._r1_push(new_pc & 0xFFFF)
                new_pc = target

        elif name == "ret":
            new_pc = self._r1_pop()

        elif name == "load":
            if args:
                # Immediate address: push value from mem[addr]
                addr = args[0] & 0xFFFF
                val = self.memory.read_data(addr, 2) if addr < 65534 else 0
                self._r1_push(val)
            else:
                # TOS-indirect: replace TOS with value at address pointed to by TOS
                addr = self._r1_pop() & 0xFFFF
                val = self.memory.read_data(addr, 2) if addr < 65534 else 0
                self._r1_push(val)

        elif name == "loadf":
            fr = self.registers.get("FR", 0)
            self._r1_push(fr & 0xFFFF)

        elif name == "store":
            if args:
                # Immediate address: pop TOS, store at addr
                addr = args[0] & 0xFFFF
                val = self._r1_pop()
                self.memory.write_data(addr, val & 0xFFFF, 2)
            else:
                # TOS-indirect: pop addr, pop val, store val at addr
                addr = self._r1_pop() & 0xFFFF
                val = self._r1_pop()
                self.memory.write_data(addr, val & 0xFFFF, 2)

        elif name == "storef":
            val = self._r1_pop()
            self.registers["FR"] = val & 0xFFFF

        elif name == "push":
            # Push to hardware stack (SP), separate from TOS stack
            if args:
                val = args[0] & 0xFFFF
            else:
                val = self._r1_pop()
            sp = self.registers.get("SP", 65535)
            self.memory.write_data(sp - 2, val, 2)
            self.registers["SP"] = sp - 2

        elif name == "pushf":
            fr = self.registers.get("FR", 0)
            sp = self.registers.get("SP", 65535)
            self.memory.write_data(sp - 2, fr & 0xFFFF, 2)
            self.registers["SP"] = sp - 2

        elif name == "pop":
            sp = self.registers.get("SP", 65535)
            val = self.memory.read_data(sp, 2)
            self.registers["SP"] = sp + 2
            self._r1_push(val)

        elif name == "popf":
            sp = self.registers.get("SP", 65535)
            val = self.memory.read_data(sp, 2)
            self.registers["SP"] = sp + 2
            self.registers["FR"] = val & 0xFFFF

        self.set_pc(new_pc)

    # ─── Fetch / decode / execute ─────────────────────────────────────────────

    def fetch(self) -> bytearray:
        return bytearray()

    def decode_and_execute(self):
        if self.halted or self.is_input_active:
            return

        pc = self.get_pc()
        bit_offset = pc * self.isa_bit_size

        bit_str = self._read_bits(bit_offset, 64)

        isa_name = self.isa.name.lower()
        opcode_len = {"risc1": 6, "risc2": 8, "risc3": 6, "cisc": 8}.get(isa_name, 8)
        opcode_str = bit_str[:opcode_len]

        inst_def = self.isa.get_instruction_by_opcode(opcode_str)
        if not inst_def:
            self.halted = True
            return

        if inst_def.name == "halt":
            self.halted = True
            return

        operands_values = []
        pc_inc = {"risc1": 1, "risc2": 1, "risc3": 2, "cisc": 1}.get(isa_name, 1)

        if isa_name == "cisc":
            cisc_styles = {
                "000": (1, 0), "001": (0, 0), "010": (0, 1), "011": (2, 0),
                "100": (1, 1), "101": (2, 1), "110": (1, 2),
            }
            reg_count, const_count = cisc_styles.get(opcode_str[:3], (0, 0))

            ptr = 8
            long_regs = []
            if reg_count > 0:
                reg_bits = bit_str[ptr:ptr + 8]
                if reg_count == 2:
                    long_regs = [reg_bits[3:6], reg_bits[:3]]
                else:
                    long_regs = [reg_bits[:3]]
                ptr += 8
                pc_inc += 1

            long_imms = []
            for _ in range(const_count):
                long_imms.append(bit_str[ptr:ptr + 16])
                ptr += 16
                pc_inc += 2
            long_imms.reverse()

            for operand in inst_def.operands:
                if operand == "reg":
                    operands_values.append(long_regs.pop())
                elif operand == "imm":
                    operands_values.append(long_imms.pop())
                elif operand == "memreg":
                    operands_values.append(long_regs.pop())
                elif operand == "memregoff":
                    operands_values.append((long_regs.pop(), long_imms.pop()))
                elif operand == "one":
                    operands_values.append(f"{1:016b}")

        elif isa_name == "risc3":
            start_point = 5 if inst_def.name in ["mov_low", "mov_high"] else 6
            ptr = start_point
            for operand in inst_def.operands:
                if operand == "reg":
                    operands_values.append(bit_str[ptr:ptr + 3])
                    ptr += 3
                elif operand.startswith("imm"):
                    length = int(operand[3:])
                    operands_values.append(bit_str[ptr:ptr + length])
                    ptr += length
                elif operand == "memreg":
                    operands_values.append(bit_str[ptr:ptr + 3])
                    ptr += 3
            pc_inc = 2

        elif isa_name in ["risc1", "risc2"]:
            if opcode_str[0] == '1':  # has immediate constant
                imm_len = 12 if isa_name == "risc1" else 16
                imm_bits = bit_str[opcode_len:opcode_len + imm_len]
                operands_values.append(imm_bits)
                pc_inc += 2

        self._execute_instruction(inst_def, operands_values, pc, pc_inc)

    def _execute_instruction(self, inst_def: InstructionDef, operands: list, pc: int, pc_inc: int):
        isa_name = self.isa.name.lower()
        name = inst_def.name

        # Build register encoding map: encoding -> register name
        reg_map = {}
        for code, reg in self.isa.registers.items():
            if reg.encoding:
                reg_map[reg.encoding] = reg.name

        new_pc = pc + pc_inc

        # Decode operand bit-strings into integer values
        args = []
        for op in operands:
            if isinstance(op, tuple):  # memregoff: (reg_enc, imm_bits)
                rname = reg_map.get(op[0], "R00")
                rval = self.registers.get(rname, 0)
                off = twos_complement(int(op[1], 2), 16)
                addr = (rval + off) & 0xFFFF
                val = self.memory.read_data(addr, 2) if addr < 65534 else 0
                args.append(val)
            elif len(op) == 3:  # 3-bit register encoding
                rname = reg_map.get(op, "R00")
                args.append(self.registers.get(rname, 0))
            else:  # immediate
                args.append(twos_complement(int(op, 2), len(op)))

        # ─── RISC1 (stack ISA) ────────────────────────────────────────────────
        if isa_name == "risc1":
            self._execute_risc1(inst_def, args, pc, pc_inc)
            return

        # ─── RISC2 (accumulator ISA) ──────────────────────────────────────────
        if isa_name == "risc2":
            self._execute_risc2(inst_def, args, operands, reg_map, pc, pc_inc)
            return

        # ─── RISC3 (register ISA) ─────────────────────────────────────────────
        if isa_name == "risc3":
            self._execute_risc3(inst_def, args, operands, reg_map, pc, pc_inc)
            return

        # ─── CISC ─────────────────────────────────────────────────────────────
        self._execute_cisc(inst_def, args, operands, reg_map, pc, pc_inc)

    # ─── RISC2 (accumulator) ─────────────────────────────────────────────────

    def _execute_risc2(self, inst_def: InstructionDef, args: list, operands: list, reg_map: dict, pc: int, pc_inc: int):
        name = inst_def.name
        new_pc = pc + pc_inc
        do_jump = False

        if name == "halt":
            self.halted = True
            return

        elif name == "nop":
            pass

        elif name == "mov":
            # acc = imm
            if args:
                self.registers["ACC"] = args[0] & 0xFFFF

        elif name in ["add", "sub", "mul", "div", "and", "or", "xor"]:
            acc = self.registers.get("ACC", 0)
            op2 = args[0] if args else self.registers.get("ACC", 0)
            if name == "add":
                res = acc + op2
            elif name == "sub":
                res = acc - op2
            elif name == "mul":
                res = acc * op2
            elif name == "div":
                res = (acc // op2) if op2 != 0 else 0
            elif name == "and":
                res = acc & op2
            elif name == "or":
                res = acc | op2
            elif name == "xor":
                res = acc ^ op2
            else:
                res = 0
            self._update_flags(res, acc, op2, 16, is_sub=(name == "sub"))
            self.registers["ACC"] = res & 0xFFFF

        elif name == "not":
            acc = self.registers.get("ACC", 0)
            res = (~acc) & 0xFFFF
            self.registers["ACC"] = res

        elif name == "lsh":
            acc = self.registers.get("ACC", 0)
            shift = args[0] if args else 0
            self.registers["ACC"] = (acc << shift) & 0xFFFF

        elif name == "rsh":
            acc = self.registers.get("ACC", 0)
            shift = args[0] if args else 0
            self.registers["ACC"] = (acc >> shift) & 0xFFFF

        elif name == "inc":
            acc = self.registers.get("ACC", 0)
            res = (acc + 1) & 0xFFFF
            self._update_flags(acc + 1, acc, 1, 16)
            self.registers["ACC"] = res

        elif name == "dec":
            acc = self.registers.get("ACC", 0)
            res = (acc - 1) & 0xFFFF
            self._update_flags(acc - 1, acc, 1, 16, is_sub=True)
            self.registers["ACC"] = res

        elif name in ["cmp", "test"]:
            acc = self.registers.get("ACC", 0)
            op2 = args[0] if args else 0
            self._update_flags(acc - op2, acc, op2, 16, is_sub=True)

        elif name in ["jmp", "je", "jne", "jg", "jge", "jl", "jle"]:
            do_jump = True
            cond = False
            z = self.get_flag("Z")
            s = self.get_flag("S")
            o = self.get_flag("O")
            if name == "jmp":
                cond = True
            elif name == "je":
                cond = z
            elif name == "jne":
                cond = not z
            elif name == "jg":
                cond = (s == o) and not z
            elif name == "jge":
                cond = (s == o)
            elif name == "jl":
                cond = (s != o)
            elif name == "jle":
                cond = (s != o) or z
            if cond:
                dist = args[0] if args else 0
                new_pc = pc + dist
            else:
                do_jump = False

        elif name == "push":
            val = self.registers.get("ACC", 0) if not args else args[0]
            sp = self.registers.get("SP", 65535)
            self.memory.write_data(sp - 2, val & 0xFFFF, 2)
            self.registers["SP"] = sp - 2

        elif name == "pushf":
            fr = self.registers.get("FR", 0)
            sp = self.registers.get("SP", 65535)
            self.memory.write_data(sp - 2, fr & 0xFFFF, 2)
            self.registers["SP"] = sp - 2

        elif name == "pop":
            sp = self.registers.get("SP", 65535)
            val = self.memory.read_data(sp, 2)
            self.registers["SP"] = sp + 2
            self.registers["ACC"] = val & 0xFFFF

        elif name == "popf":
            sp = self.registers.get("SP", 65535)
            val = self.memory.read_data(sp, 2)
            self.registers["SP"] = sp + 2
            self.registers["FR"] = val & 0xFFFF

        elif name == "call":
            dist = args[0] if args else self.registers.get("ACC", 0)
            sp = self.registers.get("SP", 65535)
            self.memory.write_data(sp - 2, new_pc & 0xFFFF, 2)
            self.registers["SP"] = sp - 2
            new_pc = pc + dist
            do_jump = True

        elif name == "ret":
            sp = self.registers.get("SP", 65535)
            new_pc = self.memory.read_data(sp, 2)
            self.registers["SP"] = sp + 2
            do_jump = True

        elif name == "load":
            if args:
                addr = args[0] & 0xFFFF
                self.registers["ACC"] = self.memory.read_data(addr, 2) & 0xFFFF

        elif name == "loadf":
            self.registers["ACC"] = self.registers.get("FR", 0) & 0xFFFF

        elif name == "loadi":
            ir = self.registers.get("IR", 0)
            self.registers["ACC"] = ir & 0xFFFF

        elif name == "store":
            if args:
                addr = args[0] & 0xFFFF
            else:
                addr = self.registers.get("IR", 0) & 0xFFFF
            self.memory.write_data(addr, self.registers.get("ACC", 0) & 0xFFFF, 2)

        elif name == "storef":
            self.registers["FR"] = self.registers.get("ACC", 0) & 0xFFFF

        elif name == "storei":
            self.registers["IR"] = self.registers.get("ACC", 0) & 0xFFFF

        elif name == "out":
            # acc variant or immediate port with acc value
            char_val = self.registers.get("ACC", 0) & 0xFF
            if 0 < char_val < 128:
                self.output_buffer += chr(char_val)

        elif name == "in":
            self.is_input_active = True

        elif name == "pushi":
            ir = self.registers.get("IR", 0)
            sp = self.registers.get("SP", 65535)
            self.memory.write_data(sp - 2, ir & 0xFFFF, 2)
            self.registers["SP"] = sp - 2

        elif name == "popi":
            sp = self.registers.get("SP", 65535)
            val = self.memory.read_data(sp, 2)
            self.registers["SP"] = sp + 2
            self.registers["IR"] = val & 0xFFFF

        self.set_pc(new_pc)

    # ─── RISC3 (register-register) ───────────────────────────────────────────

    def _execute_risc3(self, inst_def: InstructionDef, args: list, operands: list, reg_map: dict, pc: int, pc_inc: int):
        name = inst_def.name
        new_pc = pc + pc_inc
        do_jump = False

        if name == "halt":
            self.halted = True
            return

        elif name == "nop":
            pass

        elif name in ["add", "sub", "mul", "div", "and", "or", "xor", "lsh", "rsh"]:
            if len(args) >= 3:
                dest = reg_map.get(operands[0], "R00")
                op1, op2 = args[1], args[2]
            elif len(args) >= 2:
                dest = reg_map.get(operands[0], "R00")
                op1, op2 = args[0], args[1]
            else:
                self.set_pc(new_pc)
                return

            if name == "add":
                res = op1 + op2
            elif name == "sub":
                res = op1 - op2
            elif name == "mul":
                res = op1 * op2
            elif name == "div":
                res = (op1 // op2) if op2 != 0 else 0
            elif name == "and":
                res = op1 & op2
            elif name == "or":
                res = op1 | op2
            elif name == "xor":
                res = op1 ^ op2
            elif name == "lsh":
                res = op1 << op2
            elif name == "rsh":
                res = op1 >> op2
            else:
                res = 0
            self._update_flags(res, op1, op2, 16, is_sub=(name == "sub"))
            if len(operands) > 0 and len(operands[0]) == 3:
                dest = reg_map.get(operands[0], "R00")
            self.registers[dest] = res & 0xFFFF

        elif name == "addc":
            if len(args) >= 2:
                dest = reg_map.get(operands[0], "R00")
                c = 1 if self.get_flag("C") else 0
                res = args[0] + args[1] + c
                self._update_flags(res, args[0], args[1], 16)
                self.registers[dest] = res & 0xFFFF

        elif name == "not":
            if args:
                dest = reg_map.get(operands[0], "R00")
                res = (~args[-1]) & 0xFFFF
                self.registers[dest] = res

        elif name == "mov":
            if len(args) >= 2:
                dest = reg_map.get(operands[0], "R00")
                self.registers[dest] = args[1] & 0xFFFF
            elif len(args) == 1:
                dest = reg_map.get(operands[0], "R00")
                self.registers[dest] = args[0] & 0xFFFF

        elif name == "mov_low":
            if args:
                dest = reg_map.get(operands[0], "R00")
                self.registers[dest] = args[-1] & 0xFF

        elif name == "mov_high":
            if args:
                dest = reg_map.get(operands[0], "R00")
                cur = self.registers.get(dest, 0)
                self.registers[dest] = (cur & 0x00FF) | ((args[-1] & 0xFF) << 8)

        elif name in ["cmp", "test"]:
            if len(args) >= 2:
                self._update_flags(args[0] - args[1], args[0], args[1], 16, is_sub=True)

        elif name in ["jmp", "je", "jne", "jg", "jge", "jl", "jle"]:
            do_jump = True
            cond = False
            z = self.get_flag("Z")
            s = self.get_flag("S")
            o = self.get_flag("O")
            if name == "jmp":
                cond = True
            elif name == "je":
                cond = z
            elif name == "jne":
                cond = not z
            elif name == "jg":
                cond = (s == o) and not z
            elif name == "jge":
                cond = (s == o)
            elif name == "jl":
                cond = (s != o)
            elif name == "jle":
                cond = (s != o) or z
            if cond:
                dist = args[0] if args else 0
                new_pc = pc + dist
            else:
                do_jump = False

        elif name == "push":
            if args:
                sp = self.registers.get("SP", 65535)
                self.memory.write_data(sp - 2, args[0] & 0xFFFF, 2)
                self.registers["SP"] = sp - 2

        elif name == "pop":
            sp = self.registers.get("SP", 65535)
            val = self.memory.read_data(sp, 2)
            self.registers["SP"] = sp + 2
            if operands and len(operands[0]) == 3:
                dest = reg_map.get(operands[0], "R00")
                self.registers[dest] = val & 0xFFFF

        elif name == "call":
            dist = args[0] if args else 0
            self.registers["LR"] = new_pc
            new_pc = pc + dist
            do_jump = True

        elif name == "ret":
            new_pc = self.registers.get("LR", 0)
            do_jump = True

        elif name == "load":
            if len(args) >= 2:
                dest = reg_map.get(operands[0], "R00")
                addr = args[1] & 0xFFFF
                self.registers[dest] = self.memory.read_data(addr, 2) & 0xFFFF
            elif args:
                dest = reg_map.get(operands[0], "R00")
                addr = args[0] & 0xFFFF
                self.registers[dest] = self.memory.read_data(addr, 2) & 0xFFFF

        elif name == "store":
            if len(args) >= 2:
                addr = args[0] & 0xFFFF
                self.memory.write_data(addr, args[1] & 0xFFFF, 2)

        elif name == "out":
            if len(args) >= 2:
                char_val = args[1] & 0xFF
                if 0 < char_val < 128:
                    self.output_buffer += chr(char_val)
            elif args:
                char_val = args[0] & 0xFF
                if 0 < char_val < 128:
                    self.output_buffer += chr(char_val)

        elif name == "in":
            self.is_input_active = True
            if operands and len(operands[0]) == 3:
                self.input_result_destination = reg_map.get(operands[0], "R00")

        self.set_pc(new_pc)

    # ─── CISC ─────────────────────────────────────────────────────────────────

    def _execute_cisc(self, inst_def: InstructionDef, args: list, operands: list, reg_map: dict, pc: int, pc_inc: int):
        name = inst_def.name
        new_pc = pc + pc_inc
        do_jump = False

        if name == "halt":
            self.halted = True
            return

        elif name == "nop":
            pass

        elif name == "mov":
            if len(args) >= 2:
                if isinstance(operands[0], tuple):
                    # memregoff dest
                    rname = reg_map.get(operands[0][0], "R00")
                    rval = self.registers.get(rname, 0)
                    off = twos_complement(int(operands[0][1], 2), 16)
                    addr = (rval + off) & 0xFFFF
                    self.memory.write_data(addr, args[1] & 0xFFFF, 2)
                elif len(operands[0]) == 3:
                    dest = reg_map.get(operands[0], "R00")
                    self.registers[dest] = args[1] & 0xFFFF
            elif len(args) == 1 and operands:
                if not isinstance(operands[0], tuple) and len(operands[0]) == 3:
                    dest = reg_map.get(operands[0], "R00")
                    self.registers[dest] = args[0] & 0xFFFF

        elif name in ["add", "sub", "mul", "div", "and", "or", "xor"]:
            if len(args) >= 2:
                if isinstance(operands[0], tuple):
                    rname = reg_map.get(operands[0][0], "R00")
                    rval = self.registers.get(rname, 0)
                    off = twos_complement(int(operands[0][1], 2), 16)
                    addr = (rval + off) & 0xFFFF
                    op1 = self.memory.read_data(addr, 2)
                    op2 = args[1]
                else:
                    op1, op2 = args[0], args[1]
                    dest = reg_map.get(operands[0], "R00") if operands else "R00"

                if name == "add":
                    res = op1 + op2
                elif name == "sub":
                    res = op1 - op2
                elif name == "mul":
                    res = op1 * op2
                elif name == "div":
                    res = (op1 // op2) if op2 != 0 else 0
                elif name == "and":
                    res = op1 & op2
                elif name == "or":
                    res = op1 | op2
                elif name == "xor":
                    res = op1 ^ op2
                else:
                    res = 0
                self._update_flags(res, op1, op2, 16, is_sub=(name == "sub"))

                if not isinstance(operands[0], tuple) and len(operands[0]) == 3:
                    dest = reg_map.get(operands[0], "R00")
                    self.registers[dest] = res & 0xFFFF

        elif name == "not":
            if args and operands:
                if len(operands[0]) == 3:
                    dest = reg_map.get(operands[0], "R00")
                    res = (~args[0]) & 0xFFFF
                    self.registers[dest] = res

        elif name == "lsh":
            if len(args) >= 2:
                dest = reg_map.get(operands[0], "R00") if operands else "R00"
                res = (args[0] << args[1]) & 0xFFFF
                self.registers[dest] = res

        elif name == "rsh":
            if len(args) >= 2:
                dest = reg_map.get(operands[0], "R00") if operands else "R00"
                res = (args[0] >> args[1]) & 0xFFFF
                self.registers[dest] = res

        elif name == "inc":
            if args and operands:
                if len(operands[0]) == 3:
                    dest = reg_map.get(operands[0], "R00")
                    res = (args[0] + 1) & 0xFFFF
                    self._update_flags(args[0] + 1, args[0], 1, 16)
                    self.registers[dest] = res

        elif name == "dec":
            if args and operands:
                if len(operands[0]) == 3:
                    dest = reg_map.get(operands[0], "R00")
                    res = (args[0] - 1) & 0xFFFF
                    self._update_flags(args[0] - 1, args[0], 1, 16, is_sub=True)
                    self.registers[dest] = res

        elif name in ["cmp", "test"]:
            if len(args) >= 2:
                self._update_flags(args[0] - args[1], args[0], args[1], 16, is_sub=True)

        elif name in ["jmp", "je", "jne", "jg", "jge", "jl", "jle"]:
            do_jump = True
            cond = False
            z = self.get_flag("Z")
            s = self.get_flag("S")
            o = self.get_flag("O")
            if name == "jmp":
                cond = True
            elif name == "je":
                cond = z
            elif name == "jne":
                cond = not z
            elif name == "jg":
                cond = (s == o) and not z
            elif name == "jge":
                cond = (s == o)
            elif name == "jl":
                cond = (s != o)
            elif name == "jle":
                cond = (s != o) or z
            if cond:
                dist = args[0] if args else 0
                new_pc = pc + dist
            else:
                do_jump = False

        elif name == "push":
            if args:
                sp = self.registers.get("SP", 65535)
                self.memory.write_data(sp - 2, args[0] & 0xFFFF, 2)
                self.registers["SP"] = sp - 2

        elif name == "pop":
            sp = self.registers.get("SP", 65535)
            val = self.memory.read_data(sp, 2)
            self.registers["SP"] = sp + 2
            if operands and not isinstance(operands[0], tuple) and len(operands[0]) == 3:
                dest = reg_map.get(operands[0], "R00")
                self.registers[dest] = val & 0xFFFF

        elif name == "call":
            dist = args[0] if args else 0
            sp = self.registers.get("SP", 65535)
            self.memory.write_data(sp - 2, new_pc & 0xFFFF, 2)
            self.registers["SP"] = sp - 2
            new_pc = pc + dist
            do_jump = True

        elif name == "ret":
            sp = self.registers.get("SP", 65535)
            new_pc = self.memory.read_data(sp, 2)
            self.registers["SP"] = sp + 2
            do_jump = True

        elif name == "enter":
            # ENTER n: push BP, BP = SP, SP -= n
            bp = self.registers.get("BP", 0)
            sp = self.registers.get("SP", 65535)
            self.memory.write_data(sp - 2, bp & 0xFFFF, 2)
            sp -= 2
            self.registers["BP"] = sp
            sp -= (args[0] if args else 0)
            self.registers["SP"] = sp

        elif name == "leave":
            # LEAVE: SP = BP, pop BP
            bp = self.registers.get("BP", 0)
            self.registers["SP"] = bp
            val = self.memory.read_data(bp, 2)
            self.registers["SP"] = bp + 2
            self.registers["BP"] = val & 0xFFFF

        elif name == "load":
            if len(args) >= 2:
                dest = reg_map.get(operands[0], "R00") if operands else "R00"
                addr = args[1] & 0xFFFF
                self.registers[dest] = self.memory.read_data(addr, 2) & 0xFFFF

        elif name == "store":
            if len(args) >= 2:
                addr = args[0] & 0xFFFF
                self.memory.write_data(addr, args[1] & 0xFFFF, 2)

        elif name == "out":
            if len(args) >= 2:
                char_val = args[1] & 0xFF
                if 0 < char_val < 128:
                    self.output_buffer += chr(char_val)
            elif args:
                char_val = args[0] & 0xFF
                if 0 < char_val < 128:
                    self.output_buffer += chr(char_val)

        elif name == "in":
            self.is_input_active = True
            if operands and not isinstance(operands[0], tuple) and len(operands[0]) == 3:
                self.input_result_destination = reg_map.get(operands[0], "R00")

        # SIMD stubs (load4, store4, add4, sub4, mul4, div4)
        elif name in ["load4", "store4", "add4", "sub4", "mul4", "div4"]:
            pass  # SIMD not yet implemented

        self.set_pc(new_pc)

    # ─── Step / Run ───────────────────────────────────────────────────────────

    def step(self):
        self.decode_and_execute()

    def run(self, max_cycles: int = 10000):
        from core.memory.exceptions import MemoryError as MemErr
        cycles = 0
        while not self.halted and cycles < max_cycles:
            try:
                self.step()
            except MemErr:
                self.halted = True
                break
            cycles += 1
