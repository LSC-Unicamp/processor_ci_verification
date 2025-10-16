import cocotb
from cocotb.triggers import Timer, RisingEdge, ReadWrite, ReadOnly, NextTimeStep
from cocotb.clock import Clock
from cocotb.binary import BinaryValue
from cocotb.utils import get_sim_time

import os, time
import json
import argparse
import subprocess
import re


# custom functions
import elf_reader

# Simulation parameters
RIGHT_JUSTIFIED = False
TWO_MEMORIES = True
MEM_SIZE = 524288 # 512K words of 4 bytes = 1024KB
SIMULATION_TIMEOUT_CYCLES = 100000


async def instruction_memory_model(dut, memory, fetches, start_of_text_section, end_of_text_section):
    ###############################################################################
    # import debugpy
    # listen_host, listen_port = debugpy.listen(("localhost", 5678))
    # print("Waiting for Python debugger attach on {}:{}".format(listen_host, listen_port))
    # # Suspend execution until debugger attaches
    # debugpy.wait_for_client()
    # # Break into debugger for user control
    # breakpoint()  # or debugpy.breakpoint() on 3.6 and below
    ###############################################################################
    # startup code for riscv-arch-test
    rom = [0x800000b7, # lui x1,0x80000
           0x00008067, # jalr x0, 0(x1)
           0x00000013, # nop
           0x00000013, # nop
           0x00000013] # nop in case of speculative fetches
    while True:
        await RisingEdge(dut.sys_clk)  
        await ReadWrite() # wait for signals to propagate after the clock edge

        if dut.core_cyc.value == 1 and dut.core_stb.value == 1: # active transaction
            
            raw_addr = dut.core_addr.value.integer
            simulated_addr = (raw_addr // 4) % MEM_SIZE

            if dut.core_we == 0:
                # always read data, even for write operations
                if raw_addr < 0x10:
                    dut.core_data_in.value = rom[simulated_addr]
                else:
                    dut.core_data_in.value = memory[simulated_addr] # each position in inst_memory has 4 bytes
                
                # wait for reset release
                await NextTimeStep()
                await ReadWrite()
                # it is only a fetch if it is reading the .text section
                if dut.rst_n.value == 1 and raw_addr < end_of_text_section:
                    fetches.append((raw_addr, memory[simulated_addr]))
            else:
                write_value = dut.core_data_out.value.integer
                memory[simulated_addr] = write_value
                dut._log.info("Write to the instruction memory. Possible error.")
  
            dut.core_ack.value = 1
        else:
            dut.core_ack.value = 0

async def data_memory_model(dut, memory, mem_access):
    while True:
        await RisingEdge(dut.sys_clk)  
        await ReadWrite() # wait for signals to propagate after the clock edge

        if dut.data_mem_cyc.value == 1 and dut.data_mem_stb.value == 1: # active transaction

            raw_addr = dut.data_mem_addr.value.integer
            simulated_addr = (raw_addr // 4) % MEM_SIZE

            # always read data, even for write operations
            # each position in inst_memory has 4 bytes
            if RIGHT_JUSTIFIED: # lb and lh instructions expect data at LSB
                shift_amount = (raw_addr % 4) * 8
                dut.data_mem_data_in.value = memory[simulated_addr] >> shift_amount
            else:
                dut.data_mem_data_in.value = memory[simulated_addr]
            await NextTimeStep()
            await ReadWrite()

            if dut.data_mem_we == 1:
                # Write operation, depends on write strobe
                if dut.data_mem_wstrb.value == "1111":
                    write_value = dut.data_mem_data_out.value.integer
                    memory[simulated_addr] = write_value
                elif dut.data_mem_wstrb.value == "0011":
                    write_value = (memory[simulated_addr] & 0xFFFF0000) | (dut.data_mem_data_out.value.integer & 0x0000FFFF)
                    memory[simulated_addr] = write_value
                elif dut.data_mem_wstrb.value == "1100":
                    write_value = (memory[simulated_addr] & 0x0000FFFF) | (dut.data_mem_data_out.value.integer & 0xFFFF0000)
                    memory[simulated_addr] = write_value
                elif dut.data_mem_wstrb.value == "0001":
                    write_value = (memory[simulated_addr] & 0xFFFFFF00) | (dut.data_mem_data_out.value.integer & 0x000000FF)
                    memory[simulated_addr] = write_value
                elif dut.data_mem_wstrb.value == "0010":
                    write_value = (memory[simulated_addr] & 0xFFFF00FF) | (dut.data_mem_data_out.value.integer & 0x0000FF00)
                    memory[simulated_addr] = write_value
                elif dut.data_mem_wstrb.value == "0100":
                    write_value = (memory[simulated_addr] & 0xFF00FFFF) | (dut.data_mem_data_out.value.integer & 0x00FF0000)
                    memory[simulated_addr] = write_value
                elif dut.data_mem_wstrb.value == "1000":
                    write_value = (memory[simulated_addr] & 0x00FFFFFF) | (dut.data_mem_data_out.value.integer & 0xFF000000)
                    memory[simulated_addr] = write_value

                mem_access.append((raw_addr, write_value))

            dut.data_mem_ack.value = 1
        else:
            dut.data_mem_ack.value = 0

async def memory_model(dut, memory, fetches, mem_access, start_of_text_section, end_of_text_section):
    # startup code for riscv-arch-test
    rom = [0x800000b7, # lui x1,0x80000
           0x00008067, # jalr x0, 0(x1)
           0x00000013, # nop
           0x00000013, # nop
           0x00000013] # nop in case of speculative fetches
    while True:
        await RisingEdge(dut.sys_clk)  
        await ReadWrite() # wait for signals to propagate after the clock edge

        if dut.core_cyc.value == 1 and dut.core_stb.value == 1: # active transaction
            
            raw_addr = dut.core_addr.value.integer
            simulated_addr = (raw_addr // 4) % MEM_SIZE

            # always read data, even for write operations
            if raw_addr < 0x10:
                dut.core_data_in.value = rom[simulated_addr] 
            else:
                if RIGHT_JUSTIFIED: # lb and lh instructions expect data at LSB
                    shift_amount = (raw_addr % 4) * 8
                    dut.data_mem_data_in.value = memory[simulated_addr] >> shift_amount
                else:
                    dut.data_mem_data_in.value = memory[simulated_addr]

            await NextTimeStep()
            await ReadWrite()
            
            if dut.core_we == 0:
                # it is only a fetch if it is reading the .text section
                if dut.rst_n.value == 1 and raw_addr >= start_of_text_section and raw_addr < end_of_text_section:
                    fetches.append((raw_addr, memory[simulated_addr]))
            else:
                # Write operation, depends on write strobe
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

        
def show_signals_of_interest(dut, TWO_MEMORIES):
    if TWO_MEMORIES:
        dut._log.info("CORE_STB=%s", dut.core_stb.value)
        dut._log.info("CORE_ACK=%s", dut.core_ack.value)
        dut._log.info("CORE_ADDR=%x", dut.core_addr.value)
        dut._log.info("CORE_DATA_IN=%x", dut.core_data_in.value)
        dut._log.info("CORE_WE=%s", dut.core_we.value)
        dut._log.info("CORE_DATA_OUT=%s", dut.core_data_out.value)
        dut._log.info("DATA_MEM_CYC=%s", dut.data_mem_cyc.value)
        dut._log.info("DATA_MEM_STB=%s", dut.data_mem_stb.value)
        dut._log.info("DATA_MEM_ADDR=%s", dut.data_mem_addr.value)
        dut._log.info("DATA_MEM_DATA_IN=%s", dut.data_mem_data_in.value)
        dut._log.info("DATA_MEM_WE=%s", dut.data_mem_we.value)
        dut._log.info("DATA_MEM_DATA_OUT=%s", dut.data_mem_data_out.value)
        dut._log.info("DATA_MEM_WSTRB=%s", dut.data_mem_wstrb.value)
        dut._log.info("")
    else:
        dut._log.info("CORE_STB=%s", dut.core_stb.value)
        dut._log.info("CORE_ADDR=%s", dut.core_addr.value)
        dut._log.info("CORE_DATA_IN=%s", dut.core_data_in.value)
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

# Used only at debbugging
async def debug_print(dut):
    while True:
        await NextTimeStep()
        await ReadOnly()
        dut._log.info("At time %.2f ns" % get_sim_time(units="ns"))
        dut._log.info("core_stb=%s", dut.core_stb.value)
        dut._log.info("core_ack=%s", dut.core_ack.value)
        dut._log.info("instr_req=%s", dut.instr_req.value)
        dut._log.info("instr_resp=%s", dut.instr_resp.value)
        dut._log.info("")



@cocotb.test()
async def execution_trace(dut):

    # cocotb.start_soon(debug_print(dut))
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

    # Start memory, reset register file, get tohost symbol ###########################################################

    if TWO_MEMORIES:
        # Initialize instruction memory from ELF
        filename = os.environ.get("ELF")
        instruction_memory = elf_reader.load_memory(MEM_SIZE, filename)
        data_memory = elf_reader.load_data_memory(MEM_SIZE, filename)

        start_of_text_section, end_of_text_section = elf_reader.get_text_section_addr(filename)


        cocotb.start_soon(instruction_memory_model(dut, instruction_memory, fetches, start_of_text_section, end_of_text_section))
        cocotb.start_soon(data_memory_model(dut, data_memory, mem_access))
    else:
        # Initialize memory from ELF
        filename = os.environ.get("ELF")
        memory = elf_reader.load_memory(MEM_SIZE,filename)

        start_of_text_section, end_of_text_section = elf_reader.get_text_section_addr(filename)

        cocotb.start_soon(memory_model(dut, memory, fetches, mem_access, start_of_text_section, end_of_text_section))

    # get tohost symbol to detect end of program
    filename = os.environ.get("ELF")
    tohost_addr_raw = elf_reader.get_tohost_address(filename)
    tohost_addr = (tohost_addr_raw // 4) % MEM_SIZE

    # First, determine which registers exist by checking if they can be accessed
    # rvx, for example, does not have x0
    reg_file = resolve_path(dut, os.environ.get("REGFILE"))
    available_regs = []
    for i in range(32):
        try:
            # Test if register exists by trying to access it
            _ = reg_file[i].value
            available_regs.append(i)
        except (IndexError, AttributeError):
            # Register doesn't exist, skip it
            continue

    for i in available_regs:
        reg_file[i].value = 0

    ##############################################################################################

    await wait_cycles(dut.sys_clk, 5)
    dut.rst_n.value = 1
    await ReadWrite()  # Wait for the signals to propagate after reset

    # This is used to check for register file changes
    old_regfile = {}
    for i in available_regs:
        old_regfile[i] = reg_file[i].value

   # Main simulation loop
    for _ in range(SIMULATION_TIMEOUT_CYCLES):
        show_signals_of_interest(dut, TWO_MEMORIES)
        
        for i in available_regs:
            if reg_file[i].value != old_regfile[i]:
                regfile_commits.append((i, reg_file[i].value.integer))

        stop_condition = False
        if TWO_MEMORIES:
            stop_condition = data_memory[tohost_addr] == 1
        else:
            stop_condition = memory[tohost_addr] == 1
        if stop_condition:
            dut._log.info("ToHost write detected. Stop simulation.")
            break

        for i in available_regs:
            old_regfile[i] = reg_file[i].value

        await RisingEdge(dut.sys_clk)
        await ReadWrite() # Wait for the memory to react

    # riscv arch test needed a jump to 0x80000000. Remove the commit of the startup code
    regfile_commits.pop(0)

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

    parser = argparse.ArgumentParser(description="Run a ELF binaries and collect the fragmented execution trace.")
    parser.add_argument("--makefile","-m", required=True, type=str, help="Path to the makefile to use.")
    parser.add_argument("--src_path","-s", required=True, type=str, help="Path to the processor repository (used in the makefile).") # To be changed. Makefile should have absolute paths
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--elf_file", "-e", type=str, help="Path to a single ELF file to execute.")
    group.add_argument("--elf_folder", "-E", type=str, help="Path to the folder containing ELF files to execute.")
    
    parser.add_argument("--reg_file","-r", required=True, type=str, help="Cocotb path to the register trace file.")
    parser.add_argument("--output_dir","-o", required=True, type=str, help="Directory to store the trace files.")
    parser.add_argument("--verbose","-v", action="store_true", help="If set, the output of the make command will be shown in real-time.")

    args = parser.parse_args()
    makefile = args.makefile
    src_path = args.src_path
    elf_file = args.elf_file
    elf_folder = args.elf_folder
    reg_file = args.reg_file
    output_dir = args.output_dir

    if args.verbose:
        verbose = None  # inherit parent's stdout/stderr
    else:
        verbose = subprocess.DEVNULL  # suppress output

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

    make_command = ["make", "-f", makefile, "WAVES=1"]
    try:
        if args.elf_folder:
            subprocess.run(clean_command, check=True, env=env)
            for test_file in os.listdir(elf_folder):
                elf_file = os.path.join(elf_folder, test_file)
                if os.path.isfile(elf_file) and elf_file.endswith(".elf"):  
                    env['ELF'] = elf_file
                    
                    # Run make commands
                    result = subprocess.run(make_command, check=True, env=env, 
                       stdout=verbose, stderr=verbose)

                    # careful, this is hardcoded ############################################################
                    with open("results.xml", "r") as f:
                        content = f.read()
                        successful_simulation = "failure" not in content and "error" not in content

                    if successful_simulation:
                        print(f"\033[96mSuccessfully processed {os.path.basename(elf_file)}\033[0m")
                    else:
                        print(f"\033[91mFailed to process {os.path.basename(elf_file)}\033[0m")
        else:
            # Set ELF file in environment
            env['ELF'] = elf_file
            
            # Run clean command first
            subprocess.run(clean_command, check=True, env=env,
                           stdout=verbose, stderr=verbose)

            # Run make command with real-time colored output
            result = subprocess.run(make_command, check=True, env=env, 
                       stdout=verbose, stderr=verbose)
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while running bash command: {e}")
        print("STDOUT:")
        print(e.stdout)
        print("STDERR:")
        print(e.stderr)
