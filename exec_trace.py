import cocotb
from cocotb.triggers import Timer, RisingEdge, ReadOnly, ReadWrite
from cocotb.clock import Clock
from cocotb.binary import BinaryValue

import os, time
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


async def memory_model(dut, memory, fetches, mem_access):
    while True:
        await RisingEdge(dut.sys_clk)  
        await ReadWrite() # wait for signals to propagate after the clock edge

        if dut.core_cyc.value == 1 and dut.core_stb.value == 1: # active transaction
            
            raw_addr = dut.core_addr.value.integer
            simulated_addr = (raw_addr // 4) % 65536

            if dut.core_we == 0:
                dut.core_data_in.value = memory[simulated_addr] # each position in inst_memory has 4 bytes
                
                # instructions are only valid when reset is not active
                # program is located at the beginning of memory, less than 50 words
                if dut.rst_n.value == 1 and raw_addr < 50:
                    fetches.append((raw_addr, memory[simulated_addr]))
            else:
                # Write operation
                if dut.core_wstrb.value == "1111":
                    write_value = dut.core_data_out.value.integer
                    memory[simulated_addr] = write_value
                elif dut.core_wstrb.value == "0011":
                    write_value = (memory[simulated_addr] & 0xFFFF0000) | (dut.core_data_out.value.integer & 0x0000FFFF)
                    memory[simulated_addr] = write_value
                elif dut.core_wstrb.value == "1100":
                    write_value = (memory[simulated_addr] & 0x0000FFFF) | (dut.core_data_out.value.integer & 0xFFFF0000)
                    memory[simulated_addr] = write_value
                elif dut.core_wstrb.value == "0001":
                    write_value = (memory[simulated_addr] & 0xFFFFFF00) | (dut.core_data_out.value.integer & 0x000000FF)
                    memory[simulated_addr] = write_value
                elif dut.core_wstrb.value == "0010":
                    write_value = (memory[simulated_addr] & 0xFFFF00FF) | (dut.core_data_out.value.integer & 0x0000FF00)
                    memory[simulated_addr] = write_value
                elif dut.core_wstrb.value == "0100":
                    write_value = (memory[simulated_addr] & 0xFF00FFFF) | (dut.core_data_out.value.integer & 0x00FF0000)
                    memory[simulated_addr] = write_value
                elif dut.core_wstrb.value == "1000":
                    write_value = (memory[simulated_addr] & 0x00FFFFFF) | (dut.core_data_out.value.integer & 0xFF000000)
                    memory[simulated_addr] = write_value

                mem_access.append((raw_addr, write_value))

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
    fetches = []
    regfile_commits = []
    mem_access = []

    # Initialize and reset core
    processor_name = os.environ.get("PROC_NAME")
    dut._log.info(f"Initializing trace execution for {processor_name}...")

    cocotb.start_soon(Clock(dut.sys_clk, 1, units="ns").start())

    dut.core_data_in.value = 0
    dut.rst_n.value = 0
    await wait_cycles(dut.sys_clk, 5)

    # Initialize memory from ELF
    filename = os.environ.get("ELF")
    memory = elf_reader.load_memory(filename)
    # Append end of simulation condition:
    memory.append(19081998)    
    for _ in range(len(memory), 65536):
        memory.append(0)
    cocotb.start_soon(memory_model(dut, memory, fetches, mem_access)) # only start memory at middle of reset so there will be no xxxxx at the data_out port
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
        if fetches and fetches[-1][1] == 19081998:
            dut._log.info("End of program detected via magic value in memory. Stopping simulation.")
            break


    # finished simulation, write trace to file
    src_path = os.getenv("SRCPATH")
    processor_name = os.path.basename(src_path.rstrip('/'))

    output_dir = os.environ.get("OUTPUT_DIR")
    os.makedirs(output_dir, exist_ok=True)

    elf_basename = os.path.basename(os.environ.get('ELF'))
    elf_name_without_ext = os.path.splitext(elf_basename)[0]
    trace_file_path = os.path.join(output_dir, f"{elf_name_without_ext}.fragmented.json")
    with open(trace_file_path, "w") as trace_file:
        program_name = os.path.basename(os.environ.get("ELF"))
        trace_data = {
            "comment": f"Trace for {program_name} on {processor_name}",
            "fetches": fetches,
            "regfile_commits": regfile_commits,
            "memory_accesses": mem_access
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
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--elf_file", "-e", type=str, help="Path to a single ELF file to execute.")
    group.add_argument("--elf_folder", "-E", type=str, help="Path to a folder containing ELF files to execute.")
    
    parser.add_argument("--reg_file","-r", required=True, type=str, help="Cocotb path to the register trace file.")
    parser.add_argument("--output_dir","-o", required=True, type=str, help="Directory to store the trace files.")

    args = parser.parse_args()
    makefile = args.makefile
    src_path = args.src_path
    elf_file = args.elf_file
    elf_folder = args.elf_folder
    reg_file = args.reg_file
    output_dir = args.output_dir

    # make sure make command will have access to the cocotb_verification files even if called from another directory
    exec_trace_path = os.path.abspath(os.path.join(os.path.dirname(__file__)))
    
    # Prepare environment variables
    env = os.environ.copy()
    env['PYTHONPATH'] = exec_trace_path
    env['MODULE'] = 'exec_trace'
    env['SRCPATH'] = src_path
    env['REGFILE'] = args.reg_file
    env['OUTPUT_DIR'] = output_dir
    
    # Force colored output for tools that support it
    env['FORCE_COLOR'] = '1'
    env['CLICOLOR_FORCE'] = '1'
    env['TERM'] = 'xterm-256color'
    
    clean_command = ["make", "-f", makefile, "clean"]

    make_command = ["make", "-f", makefile]
    try:
        if args.elf_folder:
            subprocess.run(clean_command, check=True, env=env)
            for test_file in os.listdir(elf_folder):
                elf_file = os.path.join(elf_folder, test_file)
                if os.path.isfile(elf_file) and elf_file.endswith(".elf"):  
                    # Set ELF file in environment
                    # gambiarra, força a data do arquivo para disparar o make
                    os.utime(elf_file, (time.time(), time.time()))
                    env['ELF'] = elf_file
                    
                    # Run make commands
                    result = subprocess.run(make_command, check=True, env=env)
                    print(f"\033[96mProcessed {os.path.basename(elf_file)}\033[0m" + "\n")
        else:
            # Set ELF file in environment
            env['ELF'] = elf_file
            
            # Run clean command first
            subprocess.run(clean_command, check=True, env=env)
            
            # Run make command with real-time colored output
            result = subprocess.run(make_command, check=True, env=env)
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while running bash command: {e}")
        print("STDOUT:")
        print(e.stdout)
        print("STDERR:")
        print(e.stderr)
