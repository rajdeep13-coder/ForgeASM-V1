import os
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from core.isa.exceptions import InvalidISAError, InvalidInstructionError

@dataclass
class RegisterDef:
    name: str
    is_general_purpose: bool
    encoding: str
    description: str

@dataclass
class InstructionDef:
    opcode: str
    name: str
    result_dest: List[str]  # e.g., ["tos", "memtos"]
    operands: List[str]     # e.g., ["imm"]

class ISA:
    def __init__(self, name: str):
        self.name = name
        self.registers: Dict[str, RegisterDef] = {}
        self.instructions: Dict[str, InstructionDef] = {}
        self.instruction_by_name: Dict[str, List[InstructionDef]] = {}
        
        self._load_definitions()

    def _load_definitions(self):
        base_dir = os.path.dirname(__file__)
        
        # Load registers
        with open(os.path.join(base_dir, 'registers.json'), 'r') as f:
            reg_data = json.load(f)
            if self.name not in reg_data:
                raise InvalidISAError(f"ISA '{self.name}' not found in registers.json")
            
            for reg in reg_data[self.name]:
                r = RegisterDef(
                    name=reg[0],
                    is_general_purpose=bool(reg[1]),
                    encoding=reg[2],
                    description=reg[3]
                )
                self.registers[r.name.upper()] = r

        # Load instructions
        with open(os.path.join(base_dir, 'instructions.json'), 'r') as f:
            inst_data = json.load(f)
            if self.name not in inst_data:
                raise InvalidISAError(f"ISA '{self.name}' not found in instructions.json")
            
            for opcode, inst in inst_data[self.name].items():
                i = InstructionDef(
                    opcode=opcode,
                    name=inst[0],
                    result_dest=inst[1] if isinstance(inst[1], list) else [inst[1]],
                    operands=inst[2] if len(inst) > 2 else []
                )
                self.instructions[opcode] = i
                
                if i.name not in self.instruction_by_name:
                    self.instruction_by_name[i.name] = []
                self.instruction_by_name[i.name].append(i)

    def get_register(self, name: str) -> Optional[RegisterDef]:
        return self.registers.get(name.upper())

    def get_instruction_by_opcode(self, opcode: str) -> Optional[InstructionDef]:
        return self.instructions.get(opcode)

    def get_instructions_by_name(self, name: str) -> List[InstructionDef]:
        return self.instruction_by_name.get(name.lower(), [])
