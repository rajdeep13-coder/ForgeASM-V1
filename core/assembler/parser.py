import re
from dataclasses import dataclass
from typing import List, Dict, Any, Union
from core.assembler.exceptions import AssemblerError

@dataclass
class ParsedLine:
    line_number: int
    original_text: str
    instruction: str
    operands: List[str]

class Parser:
    """
    Parses assembly code into intermediate representation and extracts labels/directives.
    """
    def __init__(self):
        self.jump_labels: Dict[str, int] = {}
        self.mov_labels: Dict[str, Union[int, List[int]]] = {}
        
    def parse(self, text: str) -> List[ParsedLine]:
        lines = text.split('\n')
        parsed_lines = []
        
        for idx, raw_line in enumerate(lines):
            line_num = idx + 1
            line = raw_line.strip()
            
            if not line or line.startswith('#'):
                continue
                
            # Process labels and directives
            if line.startswith('.'):
                self._process_directive(line[1:], line_num, raw_line, len(parsed_lines))
                continue
                
            # It's an instruction
            # Format: instr op1, op2, op3
            parts = line.split(None, 1)
            instruction = parts[0]
            operands = []
            if len(parts) > 1:
                # split by comma and strip spaces
                operands = [op.strip() for op in parts[1].split(',') if op.strip()]
                
            parsed_lines.append(ParsedLine(
                line_number=line_num,
                original_text=raw_line,
                instruction=instruction,
                operands=operands
            ))
            
        return parsed_lines

    def _process_directive(self, line: str, line_number: int, original_text: str, current_instr_index: int):
        words = line.split()
        if not words:
            raise AssemblerError("Empty directive", line_number, original_text)
            
        label = words[0]
        if not label.isalnum() and not all(c.isalnum() or c == '_' for c in label):
            raise AssemblerError(f"Invalid label name: {label}", line_number, original_text)
            
        if label in self.jump_labels or label in self.mov_labels:
            raise AssemblerError(f"Duplicate label: {label}", line_number, original_text)
            
        if len(words) == 1:
            # Jump label
            self.jump_labels[label] = current_instr_index
        elif len(words) >= 3:
            # Data directive e.g., label db value
            directive_type = words[1].lower()
            if directive_type not in ['db', 'dw', 'word', 'byte']:
                raise AssemblerError(f"Unknown directive: {directive_type}", line_number, original_text)
            
            is_byte = directive_type in ['db', 'byte']
            value_str = ' '.join(words[2:])
            
            try:
                decoded_val = self._decode_directive_value(is_byte, value_str)
                self.mov_labels[label] = decoded_val
            except ValueError as e:
                raise AssemblerError(str(e), line_number, original_text)
        else:
            raise AssemblerError("Invalid directive format. Use '.label' or '.label db value'", line_number, original_text)

    def _decode_directive_value(self, is_byte: bool, value: str) -> Union[int, List[int]]:
        limits = (-127, 255) if is_byte else (-32768, 65535)
        
        # Try integer
        try:
            val = int(value, 0) # handles hex, bin, dec automatically if properly prefixed (0x, 0b)
            if limits[0] <= val <= limits[1]:
                return val
            else:
                raise ValueError(f"Value out of bounds for {'byte' if is_byte else 'word'}")
        except ValueError:
            pass
            
        # Try string
        if value.startswith('"') and value.endswith('"'):
            inner = value[1:-1]
            # simplified string decoding for now
            return [ord(c) for c in inner]
            
        raise ValueError(f"Invalid directive value: {value}")
