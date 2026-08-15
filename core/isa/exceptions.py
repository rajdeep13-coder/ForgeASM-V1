class ISAError(Exception):
    """Base exception for ISA-related errors."""
    pass

class InvalidISAError(ISAError):
    """Raised when an invalid ISA is requested."""
    pass

class InvalidInstructionError(ISAError):
    """Raised when an instruction is invalid for the current ISA."""
    pass
