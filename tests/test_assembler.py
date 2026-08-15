import pytest
from core.isa.isa_def import ISA
from core.assembler.assembler import Assembler
from core.assembler.exceptions import AssemblerError

def test_assembler_risc3():
    isa = ISA("risc3")
    assembler = Assembler(isa)
    
    # Risc3 register instruction
    # format: op(6) + operands...
    # mov R00, 15
    # mov is 100010 for imm. wait, let's just assemble and check if it parses and runs without error
    
    code = """
    mov_low R00, 15
    add R00, R01, R02
    .loop
    jmp .loop
    """
    
    binary = assembler.assemble(code)
    assert len(binary.split()) == 3
    
def test_assembler_cisc():
    isa = ISA("cisc")
    assembler = Assembler(isa)
    
    code = """
    .mydata db 5
    mov R00, .mydata
    """
    
    binary = assembler.assemble(code)
    assert len(binary.split()) > 0
    
def test_assembler_errors():
    isa = ISA("risc3")
    assembler = Assembler(isa)
    
    with pytest.raises(AssemblerError) as e:
        assembler.assemble("mov R99, 15")
    assert "Invalid register" in str(e.value)

    with pytest.raises(AssemblerError):
        assembler.assemble("jmp .unknown")
