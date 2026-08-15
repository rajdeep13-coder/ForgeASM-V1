"""Debug CISC assembler pass."""
from core.isa.isa_def import ISA
from core.assembler.assembler import Assembler

isa = ISA('cisc')
asm = Assembler(isa)

code = """mov %R00, .start
.mainloop
out $1, %R00
inc %R00
cmp %R00, .end
jle .mainloop
nop

.start db 65
.end db 91
"""

binary = asm.assemble(code)
print("PC table:", asm._pc_addr)
print()
print("Binary lines:")
for i, line in enumerate(binary.strip().split('\n')):
    print(f"  [{i:2d}] {line}  ({len(line)} bits)")

print()
print("Jump labels:", asm.parser.jump_labels)
print("Mov labels:", asm.parser.mov_labels)

# Manually compute what offset should be
pc_table = asm._pc_addr
print(f"\nPC addresses: {pc_table}")
target = asm.parser.jump_labels.get('mainloop', None)
print(f"mainloop label → instruction index {target}")
if target is not None and target < len(pc_table):
    print(f"target PC addr = {pc_table[target]}")
# jle is instruction index 4 (0=mov, 1=out, 2=inc, 3=cmp, 4=jle, 5=nop)
source = 4
if source < len(pc_table):
    print(f"jle PC addr = {pc_table[source]}")
    if target is not None and target < len(pc_table):
        offset = pc_table[target] - pc_table[source]
        print(f"Expected offset = {offset}")
