import re
import subprocess
import os
import argparse
import json

def generate_spike_trace(elf_file, output_dir):
    """
    Generates a Spike trace file by executing the given command.

    Args:
        elf_file (str): The ELF file to generate the trace from.
    Returns:
        str: Path to the generated trace file.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    trace_file = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(elf_file))[0]}.trace")
    # For some reason, --instructions=<n> makes spike stop after the last instruction in the elf, even if less than <n>.
    # Do not use the -l option
    command = f"spike --isa=rv32i --log-commits -m0x7ffff000:0x10000 {elf_file} > {trace_file} 2>&1" # spike writes to stderr
    subprocess.run(command, shell=True, check=True)

    return trace_file


def parse_spike_trace(trace_file):
    """
    Reads a Spike trace file, removes warning lines, and extracts information per instruction.
    Trace example:
    ```
    warning: tohost and fromhost symbols not in ELF; can't communicate with target
    core   0: 3 0x00001000 (0x00000297) x5  0x00001000
    core   0: 3 0x00001004 (0x02028593) x11 0x00001020
    core   0: 3 0x00001008 (0xf1402573) x10 0x00000000
    core   0: 3 0x0000100c (0x0182a283) x5  0x00000000 mem 0x00001018
    core   0: 3 0x00001010 (0x00028067)
    core   0: 3 0x00000000 (0x00500593) x11 0x00000005
    core   0: 3 0x00000004 (0x00000013)
    core   0: 3 0x00000008 (0x00000013)
    core   0: 3 0x0000000c (0x00000013)
    core   0: 3 0x00000010 (0x02b02e23) mem 0x0000003c 0x00000005
    ```
    Extracted fields:
    - pc: first hex value starting with 0x
    - instr: hex inside parentheses
    - target_reg: optional, register name (xN)
    - reg_val: optional, register value (hex)
    - mem_addr: optional, memory address (hex)
    - mem_val: optional, memory value (hex)

    Returns a list of dictionaries.
    """
    results = []
    line_re = re.compile(
    r"core\s+\d+:\s+\d+\s+" # Match the prefix: "core 0: 3 " (core, core id, colon, cycle)
    r"(?P<pc>0x[0-9a-fA-F]+)\s+" # Capture program counter (PC): first hex starting with 0x
    r"\((?P<instr>0x[0-9a-fA-F]+)\)" # Capture instruction: hex value inside parentheses
    r"(?:\s+(?P<target_reg>x\d+)\s+(?P<reg_val>0x[0-9a-fA-F]+))?" # Optionally capture target register and its value. Example: " x5 0x00001000"
    r"(?:\s+mem\s+(?P<mem_addr>0x[0-9a-fA-F]+)(?:\s+(?P<mem_val>0x[0-9a-fA-F]+))?)?" # Optionally capture memory access. Example: " mem 0x00001018 0x00000005"
    )

    with open(trace_file, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.lstrip().lower().startswith("warning:"):
                continue
            m = line_re.search(line)
            if m:
                entry = {
                    "pc": int(m.group("pc"), 16),
                    "instr": int(m.group("instr"), 16),
                    "target_reg": int(m.group("target_reg")[1:]) if m.group("target_reg") else None,
                    "reg_val": int(m.group("reg_val"), 16) if m.group("reg_val") else None,
                    "mem_addr": int(m.group("mem_addr"), 16) if m.group("mem_addr") else None,
                    "mem_val": int(m.group("mem_val"), 16) if m.group("mem_val") else None,
                }
                results.append(entry)

    # Remove the debug_rom part where spike starts execution 
    filtered_results = []
    for entry in results:
        if entry["pc"] >= 0x1000 and entry["pc"] <= 0x2000:
            continue
        else:
            filtered_results.append(entry)

    # detect cleanup section of riscv-arch-test
    index = 0
    while index < len(filtered_results):
        if (filtered_results[index]["instr"] == 1048723 and # li ra, 1
        filtered_results[index+1]["instr"] == 5015          # auipc	t2,0x1
        ):
            break
        index += 1
    index += 2 # mark the sw instruction
    filtered_results = filtered_results[:index+1]

    return filtered_results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate and parse Spike trace files into a json format.")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--elf_file", "-e", type=str, help="Path to a single ELF file to execute.")
    group.add_argument("--elf_folder", "-E", type=str, help="Path to the folder containing ELF files to execute.")

    parser.add_argument("--output_dir", "-o", required=True, type=str, help="Directory to save the Spike trace files.")
    args = parser.parse_args()

    if args.elf_folder:
        for test_file in os.listdir(args.elf_folder):
            if test_file.endswith(".elf"):
                elf_path = os.path.join(args.elf_folder, test_file)
                trace_file = generate_spike_trace(elf_path, args.output_dir)
                trace_dictionary = parse_spike_trace(trace_file)
                with open(os.path.join(args.output_dir, f"{os.path.splitext(os.path.basename(trace_file))[0]}.spike.json"), "w") as f:
                    json.dump(trace_dictionary, f, indent=2)
    else:
        trace_file = generate_spike_trace(args.elf_file, args.output_dir)
        trace_dictionary = parse_spike_trace(trace_file)

        with open(os.path.join(args.output_dir, f"{os.path.splitext(os.path.basename(trace_file))[0]}.spike.json"), "w") as f:
            json.dump(trace_dictionary, f, indent=2)