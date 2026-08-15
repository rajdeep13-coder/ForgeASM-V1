class AssemblerError(Exception):
    """Base exception for assembler errors."""
    
    def __init__(self, message: str, line_number: int = None, line_text: str = None):
        self.line_number = line_number
        self.line_text = line_text
        if line_number is not None and line_text is not None:
            super().__init__(f"Line {line_number}: {message}\n\t{line_text}")
        else:
            super().__init__(message)
