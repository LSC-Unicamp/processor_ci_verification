import cocotb
from cocotb.triggers import Timer, RisingEdge, ReadOnly, ReadWrite
from cocotb.clock import Clock
from cocotb.binary import BinaryValue

import os
import json
import argparse
import subprocess
import re

# custom functions
import elf_reader

###############################################################################
# import debugpy
# listen_host, listen_port = debugpy.listen(("localhost", 5678))
# print("Waiting for Python debugger attach on {}:{}".format(listen_host, listen_port))
# # Suspend execution until debugger attaches
# debugpy.wait_for_client()
# # Break into debugger for user control
# breakpoint()  # or debugpy.breakpoint() on 3.6 and below
###############################################################################

# Global trace variables
fetches = []
regfile_commits = []
memory = []

async def memory_model(dut):
    global memory
    
    filename = os.environ.get("ELF")
    memory = elf_reader.load_memory(filename)
    # Append end of simulation condition:
    memory.append(0x000402B7)  #li   t0, 0x3FFFC    # address of last word
    memory.append(0xFFC28293)  #li   t0, 0x3FFFC    # address of last word
    memory.append(0xDEADC337)  #li   t1, 0xDEADBEEF # exit code / magic value
    memory.append(0xEEF30313)  #li   t1, 0xDEADBEEF # exit code / magic value
    memory.append(0x0062A023)  #sw   t1, 0(t0)
    for _ in range(len(memory), 65536):
        memory.append(0)

    while True:
        await RisingEdge(dut.sys_clk)  
        await ReadWrite() # wait for signals to propagate after the clock edge

        if dut.core_cyc.value == 1 and dut.core_stb.value == 1: # active transaction
            
            raw_addr = dut.core_addr.value.integer
            simulated_addr = (raw_addr // 4) % 65536

            if dut.core_we == 0:
                dut.core_data_in.value = memory[simulated_addr] # each position in inst_memory has 4 bytes
                
                # instructions are only valid when reset is not active
                if dut.rst_n.value == 1 and raw_addr < 50:
                    fetches.append((raw_addr, memory[simulated_addr]))
            else:
                # Write operation
                if dut.core_wstrb.value == "1111":
                    memory[simulated_addr] = dut.core_data_out.value.integer
                elif dut.core_wstrb.value == "0011":
                    memory[simulated_addr] = (memory[simulated_addr] & 0xFFFF0000) | (dut.core_data_out.value.integer & 0x0000FFFF)
                elif dut.core_wstrb.value == "1100":
                    memory[simulated_addr] = (memory[simulated_addr] & 0x0000FFFF) | (dut.core_data_out.value.integer & 0xFFFF0000)
                elif dut.core_wstrb.value == "0001":
                    memory[simulated_addr] = (memory[simulated_addr] & 0xFFFFFF00) | (dut.core_data_out.value.integer & 0x000000FF)
                elif dut.core_wstrb.value == "0010":
                    memory[simulated_addr] = (memory[simulated_addr] & 0xFFFF00FF) | (dut.core_data_out.value.integer & 0x0000FF00)
                elif dut.core_wstrb.value == "0100":
                    memory[simulated_addr] = (memory[simulated_addr] & 0xFF00FFFF) | (dut.core_data_out.value.integer & 0x00FF0000)
                elif dut.core_wstrb.value == "1000":
                    memory[simulated_addr] = (memory[simulated_addr] & 0x00FFFFFF) | (dut.core_data_out.value.integer & 0xFF000000)

            dut.core_ack.value = 1
        else:
            dut.core_ack.value = 0

        
def show_signals_of_interest(dut):
    dut._log.info("CORE_STB=%s", dut.core_stb.value)
    dut._log.info("CORE_ADDR=%x", dut.core_addr.value)
    dut._log.info("CORE_DATA_IN=%x", dut.core_data_in.value)
    dut._log.info("CORE_WE=%s", dut.core_we.value)
    dut._log.info("CORE_DATA_OUT=%s", dut.core_data_out.value)
    dut._log.info("CORE_WSTRB=%s", dut.core_wstrb.value)
    dut._log.info("")

async def wait_cycles(signal, num_cycles):
    for _ in range(num_cycles):
        await RisingEdge(signal)

def resolve_path(dut, path: str):
    """Resolve a string path like 'processorci_top.u_core.regs[5]' into a cocotb handle."""
    parts = path.split('.')
    # Drop the first part if it matches top-level name
    if parts[0] == dut._name:
        parts = parts[1:]

    handle = dut
    for part in parts:
        if '[' in part and ']' in part:
            # Array element, e.g. regs[5]
            name, idx = part[:-1].split('[')
            handle = getattr(handle, name)[int(idx)]
        else:
            handle = getattr(handle, part)
    return handle

@cocotb.test()
async def execution_trace(dut):

    processor_name = os.environ.get("PROC_NAME")

    # Initialize and reset core
    dut._log.info(f"Initializing trace execution for {processor_name}...")

    cocotb.start_soon(Clock(dut.sys_clk, 1, units="ns").start())

    dut.core_data_in.value = 0
    dut.rst_n.value = 0
    await wait_cycles(dut.sys_clk, 5)

    # only start memory at middle of reset so there will be no xxxxx at the data_out port
    cocotb.start_soon(memory_model(dut))
    await wait_cycles(dut.sys_clk, 5)

    dut.rst_n.value = 1
    await ReadWrite()  # Wait for the signals to propagate after reset

    # Check for register file changes
    # First, determine which registers exist by checking if they can be accessed
    # rvx, for example, does not have x0
    reg_file = resolve_path(dut, os.environ.get("REGFILE"))
    available_regs = []
    for i in range(len(reg_file)):
        try:
            # Test if register exists by trying to access it
            _ = reg_file[i].value
            available_regs.append(i)
        except (IndexError, AttributeError):
            # Register doesn't exist, skip it
            continue
   # Main simulation loop
    for _ in range(100):
        show_signals_of_interest(dut)
        
        old_regfile = {}
        for i in available_regs:
            old_regfile[i] = reg_file[i].value
            
        await RisingEdge(dut.sys_clk)
        await ReadOnly() # Wait for the memory to react

        for i in available_regs:
            if reg_file[i].value != old_regfile[i]:
                regfile_commits.append((i, reg_file[i].value.integer))
        if memory[65535] == 0xDEADBEEF:
            dut._log.info("End of program detected via magic value in memory. Stopping simulation.")
            break


    # finished simulation, write trace to file
    src_path = os.getenv("SRCPATH")
    # Remove trailing slash if present, then get the basename (directory name)
    processor_name = os.path.basename(src_path.rstrip('/'))
    output_dir = os.environ.get("OUTPUT_DIR")
    os.makedirs(output_dir, exist_ok=True)
    trace_file_path = os.path.join(output_dir, f"{processor_name}.trace")
    with open(trace_file_path, "w") as trace_file:
        program_name = os.path.basename(os.environ.get("ELF"))
        trace_file.write(f"# Trace for {program_name} on {processor_name}\n")
        trace_data = {
            "fetches": fetches,
            "regfile_commits": regfile_commits
        }
    
        json_str = json.dumps(trace_data, indent=1, separators=(',', ': '))
        # Remove line breaks inside small lists like [0,\n 5244307]
        json_str = re.sub(r'\[\s*([0-9]+),\s*([0-9]+)\s*\]', r'[\1,\2]', json_str)
        trace_file.write(json_str)



# Since cocotb cannot receive arguments,
# __main__ reads arguments and writes them to a fixed-location, temporary file
if __name__ == "__main__":
    # ###############################################################################
    # import debugpy
    # listen_host, listen_port = debugpy.listen(("localhost", 5678))
    # print("Waiting for Python debugger attach on {}:{}".format(listen_host, listen_port))
    # # Suspend execution until debugger attaches
    # debugpy.wait_for_client()
    # # Break into debugger for user control
    # breakpoint()  # or debugpy.breakpoint() on 3.6 and below
    # ###############################################################################

    parser = argparse.ArgumentParser(description="Run a ELF binary and collect the execution trace.")
    parser.add_argument("--makefile","-m", required=True, type=str, help="Path to the makefile to use.")
    parser.add_argument("--src_path","-s", required=True, type=str, help="Path to the processor repository.")
    parser.add_argument("--elf_file","-e", required=True, type=str, help="Path to the ELF file to execute.")
    parser.add_argument("--reg_file","-r", required=True, type=str, help="Path to the reference register trace file.")
    parser.add_argument("--output_dir","-o", required=True, type=str, help="Directory to store the trace files.")

    args = parser.parse_args()
    makefile = args.makefile
    src_path = args.src_path
    elf_file = args.elf_file
    reg_file = args.reg_file
    output_dir = args.output_dir

    # make sure make command will have access to the cocotb_verification files even if called from another directory
    exec_trace_path = os.path.abspath(os.path.join(os.path.dirname(__file__)))
    clean_command = f"make -f {makefile} clean"
    # SRC_PATH is used in the makefile. Should we remove this and use hard-coded paths?
    bash_command = f"""PYTHONPATH={exec_trace_path} \\
make -f {makefile} \\
MODULE=exec_trace \\
ELF={elf_file} \\
SRCPATH={src_path} \\
REGFILE={args.reg_file} \\
OUTPUT_DIR={output_dir}"""
    print("Running command:")
    print(bash_command)
    bash_command = f"{clean_command} && {bash_command}"
    try:
        result = subprocess.run(bash_command, shell=True, check=True, executable="/bin/bash", 
                               capture_output=True, text=True)
        print("STDOUT:")
        print(result.stdout)
        print("STDERR:")
        print(result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while running bash command: {e}")
        print("STDOUT:")
        print(e.stdout)
        print("STDERR:")
        print(e.stderr)
