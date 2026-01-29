# This test just defines the tohost and fromhost symbols to allow linking
# and then writes to tohost to indicate the end of simulation.

.section .tohost, "aw", @progbits
.align 3
.global tohost
tohost:
    .zero 8      # Reserve 8 bytes (uint64_t), initialized to 0

.section .fromhost, "aw", @progbits
.align 3
.global fromhost
fromhost:
    .zero 8

.section .text
.global _start
_start:
    li t0, 1
    la t1, tohost
    sw t0, 0(t1)

# Compilation command:
# riscv32-unknown-elf-gcc -Ttext=0x0 -Wl,--section-start=.tohost=0x1000 -Wl,--section-start=.fromhost=0x2000 -march=rv32i -nostdlib -nostartfiles -mabi=ilp32 -o sanity_check.elf sanity_check.s
