# ToDo
- [ ] Clone and adapt spike
- [ ] Parse spike trace
- [ ] Merge processor trace or deal with fragments?
# Potential names:
NTV: non-intrusive trace-based verification
TraceMerge:
TraceWeaver:
# How to use this Spike fork:
- Changed bootrom from 0x0:0xFFF to 0x1000:0x1FFF

`#define DEBUG_START 0x1000; #define DEBUG_END (0x2000 - 1)`

- Changed reset vector to 0x0

`#define DEFAULT_RSTVEC 0x00000000`

Compilation:

`riscv32-unknown-elf-gcc -march=rv32i -mabi=ilp32 -nostdlib -Ttext=0x0 -o program.elf program.s`

Command:

`spike --isa=rv32i -m0x0:0x2000 -l program.elf`

