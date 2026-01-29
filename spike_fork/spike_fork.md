# Generating traces using the Spike fork

This fork of Spike is dated of October 2025, and the changes were necessary to relocate the spike memory map in order to execute programs starting at address 0x0. Most processors in Processor-CI have their starting address at this position. To change the map it was required to:

Change bootrom from at `riscv/platform.h`
```C
#define DEBUG_START 0x08001000; #define DEBUG_SIZE 0x1000
```
Change reset vector at `riscv/platform.h`. A rom device is created here.
```C
#define DEFAULT_RSTVEC 0x08000000
```
Compile the assembly program with the following flags:
```bash
riscv32-unknown-elf-gcc -march=rv32i -mabi=ilp32 -nostdlib -Ttext=0x0 -o program.elf program.s`
```

Run this command for spike when there is a `tohost` symbol to end the simulation:
```
spike --isa=rv32i -m0x7ffff000:0x10000 --log-commits program.elf
```

The submodule already incorporates these changes, and `spike_trace.py` uses the correct command to invoke the modified Spike.