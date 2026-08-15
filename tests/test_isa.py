import pytest
from core.isa.isa_def import ISA, RegisterDef, InstructionDef
from core.isa.exceptions import InvalidISAError

def test_load_risc1():
    isa = ISA("risc1")
    assert isa.name == "risc1"
    
    # Test registers
    ip_reg = isa.get_register("IP")
    assert ip_reg is not None
    assert ip_reg.name == "IP"
    assert ip_reg.encoding == "010"
    assert not ip_reg.is_general_purpose
    
    # Test instructions
    halt_inst = isa.get_instruction_by_opcode("000000")
    assert halt_inst is not None
    assert halt_inst.name == "halt"
    
def test_load_cisc():
    isa = ISA("cisc")
    
    r00 = isa.get_register("R00")
    assert r00 is not None
    assert r00.is_general_purpose
    assert r00.encoding == "000"
    
    mov_insts = isa.get_instructions_by_name("mov")
    assert len(mov_insts) > 0

def test_invalid_isa():
    with pytest.raises(InvalidISAError):
        ISA("unknown_isa")
