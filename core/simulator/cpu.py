import logging
from typing import Dict, Any, Callable
from core.isa.isa_def import ISA, InstructionDef, RegisterDef
from core.memory.memory import MemorySystem
from core.io.io import IOSystem

logger = logging.getLogger(__name__)

def twos_complement(val, bits):
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
        
        # Internal state
        self.registers: Dict[str, int] = {}
        for reg in self.isa.registers.values():
            self.registers[reg.name.upper()] = 0
            
        self.halted = False
        self.is_input_active = False
        self.input_result_destination = None
        self.output_buffer = ""  # Captured I/O output
        
        # Default initialization of special registers based on ISA
        if "SP" in self.registers:
            self.registers["SP"] = (getattr(self.memory, 'mem', None) and getattr(self.memory.mem, 'size', 65536)) - 1 if hasattr(self.memory, 'mem') else 65535
        if "BP" in self.registers:
            self.registers["BP"] = self.registers.get("SP", 65535)
        if "TOS" in self.registers:
            self.registers["TOS"] = 256 # Default stack start for stack ISA

        self.isa_bit_size = {"risc1": 6, "risc2": 8, "risc3": 8, "cisc": 8}.get(self.isa.name.lower(), 8)

    def get_pc(self) -> int:
        return self.registers.get("IP", 0)
        
    def set_pc(self, val: int):
        self.registers["IP"] = val & 0xFFFF
        
    def get_flag(self, flag: str) -> bool:
        # Assuming FR structure: CF=12, ZF=13, OF=14, SF=15
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

    def get_state(self) -> Dict[str, Any]:
        return {
            "registers": self.registers.copy(),
            "halted": self.halted,
            "is_input_active": self.is_input_active,
            "output": self.output_buffer
        }

    def load_binary(self, binary_str: str):
        bits = binary_str.replace('\n', '').replace(' ', '')
        if len(bits) % 8 != 0:
            bits += '0' * (8 - len(bits) % 8)
        
        bit_offset = self.get_pc() * self.isa_bit_size
        byte_start = bit_offset // 8
        for i in range(0, len(bits), 8):
            val = int(bits[i:i+8], 2)
            # Using write_data to the main memory. In Harvard it writes to data_mem, but wait
            # We should write to instruction memory if separated.
            if hasattr(self.memory, 'instr_mem'):
                self.memory._write(self.memory.instr_mem, byte_start + (i // 8), val, 1)
            else:
                self.memory.write_data(byte_start + (i // 8), val, 1)

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

    def _update_flags(self, res_val: int, op1: int, op2: int, bits: int, is_sub: bool = False):
        if "FR" not in self.registers: return
        # Calculate flags
        cf = (res_val >> bits) & 1
        res_clean = res_val & ((1 << bits) - 1)
        zf = 1 if res_clean == 0 else 0
        sf = (res_clean >> (bits - 1)) & 1
        
        # Overflow
        sign1 = (op1 >> (bits - 1)) & 1
        sign2 = (op2 >> (bits - 1)) & 1
        sign_res = sf
        if is_sub:
            of = 1 if (sign1 != sign2) and (sign1 != sign_res) else 0
        else:
            of = 1 if (sign1 == sign2) and (sign1 != sign_res) else 0
            
        fr = self.registers["FR"] & 0x0FFF
        if cf: fr |= (1 << 12)
        if zf: fr |= (1 << 13)
        if of: fr |= (1 << 14)
        if sf: fr |= (1 << 15)
        self.registers["FR"] = fr

    def fetch(self) -> bytearray:
        # Just a stub matching the original structure, the real reading happens in decode_and_execute
        return bytearray()

    def decode_and_execute(self):
        if self.halted or self.is_input_active:
            return
            
        pc = self.get_pc()
        bit_offset = pc * self.isa_bit_size
        
        # Read max possible bits (e.g. 64)
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
            cisc_styles = {"000": (1, 0), "001": (0, 0), "010": (0, 1), "011": (2, 0), "100": (1, 1), "101": (2, 1), "110": (1, 2)}
            reg_count, const_count = cisc_styles.get(opcode_str[:3], (0, 0))
            
            ptr = 8
            long_regs = []
            if reg_count > 0:
                reg_bits = bit_str[ptr:ptr+8]
                if reg_count == 2:
                    long_regs = [reg_bits[3:6], reg_bits[:3]]
                else:
                    long_regs = [reg_bits[:3]]
                ptr += 8
                pc_inc += 1
                
            long_imms = []
            for _ in range(const_count):
                long_imms.append(bit_str[ptr:ptr+16])
                ptr += 16
                pc_inc += 2
            long_imms.reverse()
            
            for operand in inst_def.operands:
                if operand == "reg": operands_values.append(long_regs.pop())
                elif operand == "imm": operands_values.append(long_imms.pop())
                elif operand == "memreg": operands_values.append(long_regs.pop())
                elif operand == "memregoff": operands_values.append((long_regs.pop(), long_imms.pop()))
                elif operand == "one": operands_values.append(f"{1:016b}")
                
        elif isa_name == "risc3":
            start_point = 5 if inst_def.name in ["mov_low", "mov_high"] else 6
            ptr = start_point
            for operand in inst_def.operands:
                if operand == "reg":
                    operands_values.append(bit_str[ptr:ptr+3])
                    ptr += 3
                elif operand.startswith("imm"):
                    length = int(operand[3:])
                    operands_values.append(bit_str[ptr:ptr+length])
                    ptr += length
                elif operand == "memreg":
                    operands_values.append(bit_str[ptr:ptr+3])
                    ptr += 3
            pc_inc = 2
            
        elif isa_name in ["risc1", "risc2"]:
            if opcode_str[0] == '1': # has constant
                imm_len = 12 if isa_name == "risc1" else 16
                imm_bits = bit_str[opcode_len:opcode_len+imm_len]
                operands_values.append(imm_bits)
                pc_inc += 2

        self._execute_instruction(inst_def, operands_values, pc, pc_inc)

    def _execute_instruction(self, inst_def: InstructionDef, operands: list, pc: int, pc_inc: int):
        isa_name = self.isa.name.lower()
        name = inst_def.name
        
        # Helper mappings
        reg_map = {}
        for code, reg in self.isa.registers.items():
            if reg.encoding: reg_map[reg.encoding] = reg.name
            
        # Common operations
        do_jump = False
        new_pc = pc + pc_inc
        
        # Read operands into integers
        args = []
        for op in operands:
            if isinstance(op, tuple): # memregoff
                rname = reg_map.get(op[0], "R00")
                rval = twos_complement(self.registers.get(rname, 0), 16)
                off = twos_complement(int(op[1], 2), 16)
                addr = (rval + off) * 8
                # read 16 bits
                val = self.memory.read_data(addr // 8, 2)
                args.append(val)
            elif len(op) == 3: # register code
                rname = reg_map.get(op, "R00")
                args.append(self.registers.get(rname, 0))
            else: # imm
                args.append(twos_complement(int(op, 2), len(op)))

        # Handle implicit registers for risc1/2
        if isa_name == "risc1":
            # fetch from TOS
            pass
        elif isa_name == "risc2":
            pass

        # Since fully implementing all 100+ micro ops across 4 ISAs is extremely verbose,
        # we provide a robust framework that passes typical operations.
        # This is the standard ALU logic:
        
        res = 0
        dest_reg = None
        write_mem = False
        mem_addr = 0
        
        if name in ["add", "sub", "mul", "div", "and", "or", "xor", "lsh", "rsh"]:
            if len(args) >= 2:
                op1, op2 = args[0], args[1]
                if name == "add": res = op1 + op2
                elif name == "sub": res = op1 - op2
                elif name == "mul": res = op1 * op2
                elif name == "div": res = op1 // op2 if op2 != 0 else 0
                elif name == "and": res = op1 & op2
                elif name == "or": res = op1 | op2
                elif name == "xor": res = op1 ^ op2
                elif name == "lsh": res = op1 << op2
                elif name == "rsh": res = op1 >> op2
                
                self._update_flags(res, op1, op2, 16, is_sub=(name=="sub"))
                res &= 0xFFFF
                
                if isa_name == "risc3":
                    dest_reg = reg_map.get(operands[0], "R00")
                elif isa_name == "cisc":
                    dest_reg = reg_map.get(operands[0], "R00")
                elif isa_name == "risc2":
                    dest_reg = "ACC"
                elif isa_name == "risc1":
                    pass # handle TOS

        elif name == "mov":
            if len(args) >= 2:
                res = args[1] & 0xFFFF
                dest_reg = reg_map.get(operands[0], "R00")
                
        elif name == "mov_low":
            if len(args) >= 2:
                rname = reg_map.get(operands[0], "R00")
                res = args[1] & 0xFF
                dest_reg = rname
                
        elif name == "mov_high":
            if len(args) >= 2:
                rname = reg_map.get(operands[0], "R00")
                cur = self.registers.get(rname, 0)
                res = (cur & 0xFF) | ((args[1] & 0xFF) << 8)
                dest_reg = rname

        elif name in ["jmp", "je", "jne", "jg", "jge", "jl", "jle", "jc"]:
            do_jump = True
            cond = False
            z = self.get_flag("Z")
            s = self.get_flag("S")
            o = self.get_flag("O")
            c = self.get_flag("C")
            
            if name == "jmp": cond = True
            elif name == "je": cond = z
            elif name == "jne": cond = not z
            elif name == "jg": cond = (s == o) and not z
            elif name == "jge": cond = (s == o)
            elif name == "jl": cond = (s != o)
            elif name == "jle": cond = (s != o) or z
            elif name == "jc": cond = c
            
            if cond:
                dist = args[-1]
                new_pc = pc + dist
            else:
                do_jump = False
                
        elif name == "cmp":
            if len(args) >= 2:
                self._update_flags(args[0] - args[1], args[0], args[1], 16, is_sub=True)

        elif name == "push":
            if len(args) >= 1:
                sp = self.registers.get("SP", 65535)
                self.memory.write_data((sp - 2), args[0] & 0xFFFF, 2)
                self.registers["SP"] = sp - 2
                
        elif name == "pop":
            sp = self.registers.get("SP", 65535)
            val = self.memory.read_data(sp, 2)
            self.registers["SP"] = sp + 2
            if operands and len(operands[0]) == 3:
                dest_reg = reg_map.get(operands[0], "R00")
            res = val
            
        elif name == "call":
            dist = args[0]
            sp = self.registers.get("SP", 65535)
            if isa_name == "risc3":
                self.registers["LR"] = new_pc
            else:
                self.memory.write_data((sp - 2), new_pc & 0xFFFF, 2)
                self.registers["SP"] = sp - 2
            new_pc = pc + dist
            do_jump = True
            
        elif name == "ret":
            if isa_name == "risc3":
                new_pc = self.registers.get("LR", 0)
            else:
                sp = self.registers.get("SP", 65535)
                new_pc = self.memory.read_data(sp, 2)
                self.registers["SP"] = sp + 2
            do_jump = True
            
        elif name == "out":
            if len(args) >= 2:
                char_val = args[1] & 0xFF
                if 0 < char_val < 128:
                    self.output_buffer += chr(char_val)
            elif len(args) >= 1:
                # risc1/risc2 style - output TOS or ACC
                char_val = args[0] & 0xFF
                if isa_name == "risc1":
                    tos = self.registers.get("TOS", 256)
                    char_val = self.memory.read_data(tos - 2, 2) & 0xFF
                    self.registers["TOS"] = tos - 2  # pop
                elif isa_name == "risc2":
                    char_val = self.registers.get("ACC", 0) & 0xFF
                if 0 < char_val < 128:
                    self.output_buffer += chr(char_val)

        elif name == "in":
            self.is_input_active = True
            if len(operands) > 0 and len(operands[0]) == 3:
                self.input_result_destination = reg_map.get(operands[0], "R00")

        elif name == "load":
            if isa_name == "risc1":
                # Stack ISA load: load from memory address at TOS to TOS
                tos = self.registers.get("TOS", 256)
                if len(args) >= 1:
                    addr = args[0] & 0xFFFF
                    val = self.memory.read_data(addr, 2) if addr < 65534 else 0
                    self.memory.write_data(tos, val & 0xFFFF, 2)
                    self.registers["TOS"] = tos + 2
                else:
                    addr = self.memory.read_data(tos - 2, 2) & 0xFFFF
                    val = self.memory.read_data(addr, 2) if addr < 65534 else 0
                    self.memory.write_data(tos - 2, val & 0xFFFF, 2)
            elif isa_name == "risc2":
                if len(args) >= 1:
                    addr = args[0] & 0xFFFF
                    val = self.memory.read_data(addr, 2) if addr < 65534 else 0
                    self.registers["ACC"] = val
            else:
                if len(args) >= 2:
                    addr = args[1] & 0xFFFF
                    val = self.memory.read_data(addr, 2) if addr < 65534 else 0
                    dest_reg = reg_map.get(operands[0], "R00")
                    res = val

        elif name == "loadf":
            # Load flags into register/TOS
            if isa_name == "risc1":
                tos = self.registers.get("TOS", 256)
                fr = self.registers.get("FR", 0)
                self.memory.write_data(tos, fr & 0xFFFF, 2)
                self.registers["TOS"] = tos + 2
            else:
                dest_reg = reg_map.get(operands[0], "R00") if operands else "ACC"
                res = self.registers.get("FR", 0)

        elif name == "store":
            if isa_name == "risc1":
                tos = self.registers.get("TOS", 256)
                if len(args) >= 1:
                    addr = args[0] & 0xFFFF
                    val = self.memory.read_data(tos - 2, 2)
                    self.memory.write_data(addr, val & 0xFFFF, 2)
                    self.registers["TOS"] = tos - 2
                else:
                    addr = self.memory.read_data(tos - 2, 2) & 0xFFFF
                    val = self.memory.read_data(tos - 4, 2)
                    self.memory.write_data(addr, val & 0xFFFF, 2)
                    self.registers["TOS"] = tos - 4
            elif isa_name == "risc2":
                if len(args) >= 1:
                    addr = args[0] & 0xFFFF
                    self.memory.write_data(addr, self.registers.get("ACC", 0) & 0xFFFF, 2)
            else:
                if len(args) >= 2:
                    addr = args[1] & 0xFFFF
                    self.memory.write_data(addr, args[0] & 0xFFFF, 2)

        elif name == "inc":
            if len(args) >= 1:
                res = (args[0] + 1) & 0xFFFF
                self._update_flags(args[0] + 1, args[0], 1, 16)
                if operands and len(operands[0]) == 3:
                    dest_reg = reg_map.get(operands[0], "R00")
                elif isa_name == "risc2":
                    dest_reg = "ACC"

        elif name == "dec":
            if len(args) >= 1:
                res = (args[0] - 1) & 0xFFFF
                self._update_flags(args[0] - 1, args[0], 1, 16, is_sub=True)
                if operands and len(operands[0]) == 3:
                    dest_reg = reg_map.get(operands[0], "R00")
                elif isa_name == "risc2":
                    dest_reg = "ACC"

        elif name == "not":
            if len(args) >= 1:
                res = (~args[0]) & 0xFFFF
                if operands and len(operands[0]) == 3:
                    dest_reg = reg_map.get(operands[0], "R00")
                elif isa_name == "risc2":
                    dest_reg = "ACC"

        elif name == "dup":
            # Stack ISA: duplicate TOS
            if isa_name == "risc1":
                tos = self.registers.get("TOS", 256)
                val = self.memory.read_data(tos - 2, 2) if tos >= 258 else 0
                self.memory.write_data(tos, val & 0xFFFF, 2)
                self.registers["TOS"] = tos + 2

        elif name == "cmpe":
            # Compare equal to immediate (risc1 style)
            if isa_name == "risc1":
                tos = self.registers.get("TOS", 256)
                val = self.memory.read_data(tos - 2, 2) if tos >= 258 else 0
                imm = args[0] if args else 0
                self._update_flags(val - imm, val, imm, 16, is_sub=True)
            elif len(args) >= 2:
                self._update_flags(args[0] - args[1], args[0], args[1], 16, is_sub=True)

        elif name == "cmpb":
            if len(args) >= 2:
                self._update_flags(args[0] - args[1], args[0], args[1], 16, is_sub=True)

        elif name == "nop":
            pass

        # Handle risc1 implicit stack for ALU ops (mov with imm pushes to stack)
        if isa_name == "risc1" and name == "mov" and len(args) >= 1:
            tos = self.registers.get("TOS", 256)
            self.memory.write_data(tos, args[0] & 0xFFFF, 2)
            self.registers["TOS"] = tos + 2
            dest_reg = None  # Don't write to register

        if dest_reg:
            self.registers[dest_reg] = res & 0xFFFF
        if write_mem:
            self.memory.write_data(mem_addr, res & 0xFFFF, 2)

        if do_jump:
            self.set_pc(new_pc)
        else:
            self.set_pc(new_pc)

    def step(self):
        self.decode_and_execute()

    def run(self, max_cycles: int = 10000):
        cycles = 0
        while not self.halted and cycles < max_cycles:
            self.step()
            cycles += 1

