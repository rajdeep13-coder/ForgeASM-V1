class MemoryError(Exception):
    """Base exception for memory errors."""
    pass

class OutOfBoundsError(MemoryError):
    pass

class MemoryAccessError(MemoryError):
    pass
