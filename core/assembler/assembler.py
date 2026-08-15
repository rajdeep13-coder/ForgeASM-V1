from typing import List
from core.isa.isa_def import ISA, InstructionDef
from core.assembler.parser import Parser, ParsedLine
from core.assembler.exceptions import AssemblerError

class Assembler:
    def __init__(self, isa: ISA):
        self.isa = isa
        self.parser = Parser()
        
        # Instruction size lookup by ISA type
        sizes = {"risc1": 6, "risc2": 8, "risc3": 16, "cisc": 8}
        self.instruction_size = sizes.get(isa.name.lower(), 8)
        
        self.jump_labels_allowed = {"jmp", "call", "je", "jne", "jl", "jle", "jg", "jge", "jc"}
        self.mov_labels_allowed = {"mov", "load", "store", "push", "mov_low", "mov_high", "cmp", "cmpe", "cmpb", "mul", "div"}

    def assemble(self, text: str) -> str:
        parsed_lines = self.parser.parse(text)
        binary_lines = []
        
        for idx, p_line in enumerate(parsed_lines):
            binary_line = self._assemble_line(p_line, idx)
            binary_lines.append(binary_line)
            
        return "\n".join(binary_lines)

    def _assemble_line(self, p_line: ParsedLine, instr_index: int) -> str:
        candidates = self.isa.get_instructions_by_name(p_line.instruction)
        if not candidates:
            raise AssemblerError(f"Unknown instruction: {p_line.instruction}", p_line.line_number, p_line.original_text)
            
        # Try to match one of the candidates
        last_error = None
        for candidate in candidates:
            try:
                return self._encode_instruction(p_line, candidate, instr_index)
            except AssemblerError as e:
                last_error = e
                
        raise last_error or AssemblerError("No matching operand signature found", p_line.line_number, p_line.original_text)

    def _encode_instruction(self, p_line: ParsedLine, inst_def: InstructionDef, instr_index: int) -> str:
        op_types = [t for t in inst_def.operands if t != "one"]
        
        if len(p_line.operands) != len(op_types):
            raise AssemblerError(f"Expected {len(op_types)} operands, got {len(p_line.operands)}", 
                                 p_line.line_number, p_line.original_text)
                                 
        opcode = inst_def.opcode
        # special case for 5-bit opcodes
        if p_line.instruction in ["mov_low", "mov_high"] and len(opcode) > 5:
            opcode = opcode[:5]
            
        binary_part = opcode
        cisc_reg_byte = ""
        imm_bytes = ""
        
        for i, (operand, op_type) in enumerate(zip(p_line.operands, op_types)):
            encoded_parts = self._encode_operand(operand, op_type, p_line.instruction, instr_index, p_line)
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
            # Padding register byte to 8 bits if needed
            cisc_reg_byte = cisc_reg_byte.ljust(8, '0')
            return binary_part + "\n" + cisc_reg_byte + ("\n" + imm_bytes if imm_bytes else "")
            
        return binary_part

    def _encode_operand(self, operand: str, op_type: str, instr_name: str, instr_index: int, p_line: ParsedLine):
        # returns (encoded_bits, destination_type)
        # destination_type is either "reg" or "imm"
        
        if op_type in ["reg", "fr", "memreg", "simdreg"]:
            clean_op = operand.replace("[", "").replace("]", "").replace("%", "").strip()
            # Handle R00 vs 00 etc
            reg = self.isa.get_register(clean_op)
            if not reg:
                # Sometimes it might be formatted as R00, or sometimes without prefix in original code, handled implicitly
                pass
            if not reg and clean_op.startswith('R') or clean_op.startswith('r'):
                reg = self.isa.get_register(clean_op)
            if not reg:
                raise AssemblerError(f"Invalid register: {operand}", p_line.line_number, p_line.original_text)
            return [(reg.encoding, "reg")]
            
        elif op_type in ["regoff", "memregoff"]:
            # Need to parse [reg+off]
            clean = operand.replace("[", "").replace("]", "").replace("%", "").replace(" ", "")
            sign = 1
            idx = clean.find("+")
            if idx == -1:
                idx = clean.find("-")
                sign = -1
                
            if idx == -1:
                raise AssemblerError(f"Expected offset in {operand}", p_line.line_number, p_line.original_text)
                
            reg_name = clean[:idx]
            off_str = clean[idx+1:]
            
            reg = self.isa.get_register(reg_name)
            if not reg:
                raise AssemblerError(f"Invalid register: {reg_name}", p_line.line_number, p_line.original_text)
                
            try:
                # Simple parsing for offset
                if off_str.startswith('$'): off_str = off_str[1:]
                offset = int(off_str, 0) * sign
            except ValueError:
                raise AssemblerError(f"Invalid offset: {off_str}", p_line.line_number, p_line.original_text)
                
            imm_bits = self._encode_number(offset, 16, p_line)
            return [(reg.encoding, "reg"), (imm_bits, "imm")]
            
        elif op_type.startswith("imm"):
            val_str = operand
            if val_str.startswith('$'): val_str = val_str[1:]
            
            val = 0
            # Label resolution
            if val_str.startswith('.'):
                label = val_str[1:]
                if instr_name in self.jump_labels_allowed and label in self.parser.jump_labels:
                    val = self.parser.jump_labels[label] - instr_index
                elif instr_name in self.mov_labels_allowed and label in self.parser.mov_labels:
                    label_val = self.parser.mov_labels[label]
                    val = label_val[0] if isinstance(label_val, list) else label_val
                else:
                    raise AssemblerError(f"Unknown or invalid label usage: {label}", p_line.line_number, p_line.original_text)
            else:
                try:
                    val = int(val_str, 0)
                except ValueError:
                    raise AssemblerError(f"Invalid immediate: {val_str}", p_line.line_number, p_line.original_text)
            
            bit_len = {"risc1": 12, "risc2": 16, "risc3": int(op_type[3:] if len(op_type)>3 else 16), "cisc": 16}.get(self.isa.name, 16)
            
            return [(self._encode_number(val, bit_len, p_line), "imm")]
            
        raise AssemblerError(f"Unsupported operand type: {op_type}", p_line.line_number, p_line.original_text)
        
    def _encode_number(self, num: int, bit_len: int, p_line: ParsedLine) -> str:
        # Check bounds
        min_val = - (2**(bit_len - 1))
        max_val = (2**(bit_len - 1)) - 1
        # For unsigned values it can be up to 2**bit_len - 1
        if not (min_val <= num < (2**bit_len)):
            raise AssemblerError(f"Immediate {num} out of bounds for {bit_len} bits", p_line.line_number, p_line.original_text)
            
        if num < 0:
            num = (1 << bit_len) + num
            
        fmt = f"0{bit_len}b"
        return format(num, fmt)
