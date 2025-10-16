import argparse
import json
import os

# Some processor access only word-aligned addresses, while Spike provides the exact address
# This flag makes the comparison ignore the two least significant bits of store addresses and align them to word boundaries
# Needed this for tinyriscv
WORD_BOUNDARY_STORES = False

def is_load_instruction(instruction):
    load_op_code = instruction & 0b1111111 == 0b0000011 # lb, lh, lw, lbu, lhu
    return load_op_code
    
def is_store_byte_instruction(instruction):
    store_op_code = instruction & 0b1111111 == 0b0100011 # sb, sh, sw
    store_func3 = (instruction >> 12) & 0b111 == 0b000
    return store_op_code and store_func3

def is_store_half_instruction(instruction):
    store_op_code = instruction & 0b1111111 == 0b0100011 # sb, sh, sw
    store_func3 = (instruction >> 12) & 0b111 == 0b001
    return store_op_code and store_func3

def is_store_word_instruction(instruction):
    store_op_code = instruction & 0b1111111 == 0b0100011 # sb, sh, sw
    store_func3 = (instruction >> 12) & 0b111 == 0b010
    return store_op_code and store_func3

def is_branch_instruction(instruction):
    branch_op_code = instruction & 0b1111111 == 0b1100011 # beq, bne, blt, bge, bltu, bgeu
    return branch_op_code

def is_jump_instruction(instruction):
    jump_op_code = (instruction & 0b1111111 == 0b1101111) or (instruction & 0b1111111 == 0b1100111) # jal or jalr
    # write_to_zero = (instruction & 0b00000000000000000000111110000000) == 0
    return jump_op_code

def is_reg_instruction(instruction):
    op_code = instruction & 0b1111111
    reg_opcode = (  op_code == 0b0110111 or # lui
                    op_code == 0b0010111 or # auipc 
                    op_code == 0b0010011 or # addi, slti, sltiu, xori, ori, andi, slli, srli, srai
                    op_code == 0b0110011    # add, sub, sll, slt, sltu, xor, srl, sra, or, and 
                )
    return reg_opcode

def is_fence_instruction(instruction):
    fence_op_code = instruction & 0b1111111 == 0b0001111 # fence
    return fence_op_code

def reorder_superscalar_commits(spike_entry, regfile_commits, regfile_commits_index):
    """
    Look for the next commits in case the superscalar processor committed out of order.
    If it does not find a match within the next 4 commits, nothing is changed.
    """
    next_index = regfile_commits_index + 1
    while next_index < regfile_commits_index + 4 and next_index < len(regfile_commits):
        next_commit = regfile_commits[next_index]
        if next_commit[0] == spike_entry["target_reg"] and next_commit[1] == spike_entry["reg_val"]:
            # Swap the commits to bring the matching one to the current index
            regfile_commits[regfile_commits_index], regfile_commits[next_index] = regfile_commits[next_index], regfile_commits[regfile_commits_index]
            return
        next_index += 1

def generate_final_trace(spike_trace, dut_trace, elf_name):
    """
    Compares the spike trace with the dut fragmented trace to generate a final dut trace.
    If the dut trace has more fetches than needed, these are marked as speculative fetches.
    Since the simulation only detects changes to the register file, repeated writes such as
    regfile[1] <= 5
    regfile[1] <= 5
    are not detected. In this case, a correct commit is added and marked as speculative commit. 
    """
    # Generate processor/dut trace while comparing to the spike trace
    fetches_index = 0
    regfile_commits_index = 0
    memory_accesses_index = 0
    dut_trace_final = []
    spike_regfile = [0] * 32
    spike_index = 0
    while spike_index < len(spike_trace):

        spike_entry = spike_trace[spike_index]

        # dut_trace was shorter than spike_trace, probably a bug
        if fetches_index >= len(dut_trace["fetches"]):
            print(f"{elf_name} trace ended before expected (out of fetches).")
            break
        
        # filter memory reads, dut cannot detect memory reads
        if spike_entry["mem_addr"] is not None and spike_entry["mem_val"] is None:
            spike_entry["mem_addr"] = None

        # repeated writes cannot be detected. Mark them as speculative commits
        repeated_write = False
        if spike_entry["target_reg"] is not None:
            repeated_write = spike_regfile[spike_entry["target_reg"]] == spike_entry["reg_val"]

        speculative_commit = False
        if repeated_write:
            speculative_commit = True
            dut_trace["regfile_commits"].insert(regfile_commits_index, [spike_entry["target_reg"], spike_entry["reg_val"]])
            

        if (spike_entry["pc"] != dut_trace["fetches"][fetches_index][0]
            # or spike_entry["instr"] != dut_trace["fetches"][fetches_index][1]
        ):
            # Assume speculative fetch
            dut_trace_final.append({
                "pc": dut_trace["fetches"][fetches_index][0],
                "instr": dut_trace["fetches"][fetches_index][1],
                "target_reg": None,
                "reg_val": None,
                "mem_addr": None,
                "mem_val": None,
                "speculative_fetch": True,
                "speculative_commit": speculative_commit
            })
            fetches_index += 1
        else:
            # Check if the instruction is writing to the x0 register
            # Writes to x0 are not computed
            write_to_zero = (dut_trace["fetches"][fetches_index][1] & 0b00000000000000000000111110000000) == 0

            if is_load_instruction(dut_trace["fetches"][fetches_index][1]):
                if write_to_zero: # just the fetch
                    dut_trace_final.append({
                        "pc": dut_trace["fetches"][fetches_index][0],
                        "instr": dut_trace["fetches"][fetches_index][1],
                        "target_reg": None,
                        "reg_val": None,
                        "mem_addr": None,
                        "mem_val": None,
                        "speculative_fetch": False,
                        "speculative_commit": speculative_commit
                    })
                    fetches_index += 1
                    spike_index += 1
                else:
                    if regfile_commits_index >= len(dut_trace["regfile_commits"]):
                        print(f"{elf_name} trace ended before expected (out of regfile_commits).")
                        break
                    
                    reorder_superscalar_commits(spike_entry, dut_trace["regfile_commits"], regfile_commits_index)

                    dut_trace_final.append({
                        "pc": dut_trace["fetches"][fetches_index][0],
                        "instr": dut_trace["fetches"][fetches_index][1],
                        "target_reg": dut_trace["regfile_commits"][regfile_commits_index][0],
                        "reg_val": dut_trace["regfile_commits"][regfile_commits_index][1],
                        "mem_addr": None,
                        "mem_val": None,
                        "speculative_fetch": False,
                        "speculative_commit": speculative_commit
                    })
                    fetches_index += 1
                    regfile_commits_index += 1
                    spike_index += 1
                    spike_regfile[spike_entry["target_reg"]] = spike_entry["reg_val"]

            elif (is_store_byte_instruction(dut_trace["fetches"][fetches_index][1]) or
                  is_store_half_instruction(dut_trace["fetches"][fetches_index][1]) or
                  is_store_word_instruction(dut_trace["fetches"][fetches_index][1])):
                
                if memory_accesses_index >= len(dut_trace["memory_accesses"]):
                    print(f"{elf_name} trace ended before expected (out of memory accesses)")
                    break
                
                # Exract only the bytes that were actually stored (considering write strobe)
                # Spike address points to the specific bytes to be stored
                byte_shift = 8*(spike_entry["mem_addr"] & 0b11)
                aux_dut_mem_val = dut_trace["memory_accesses"][memory_accesses_index][1]
                if is_store_word_instruction(dut_trace["fetches"][fetches_index][1]):
                    aux_mem_val = (aux_dut_mem_val >> byte_shift)
                elif is_store_half_instruction(dut_trace["fetches"][fetches_index][1]):
                    aux_mem_val = (aux_dut_mem_val >> byte_shift) & 0xFFFF
                elif is_store_byte_instruction(dut_trace["fetches"][fetches_index][1]):
                    aux_mem_val = (aux_dut_mem_val >> byte_shift) & 0xFF

                dut_trace_final.append({
                    "pc": dut_trace["fetches"][fetches_index][0],
                    "instr": dut_trace["fetches"][fetches_index][1],
                    "target_reg": None,
                    "reg_val": None,
                    "mem_addr": dut_trace["memory_accesses"][memory_accesses_index][0],
                    "mem_val": aux_mem_val,
                    "speculative_fetch": False,
                    "speculative_commit": speculative_commit
                })
                fetches_index += 1
                memory_accesses_index += 1
                spike_index += 1
            elif is_branch_instruction(dut_trace["fetches"][fetches_index][1]):
                dut_trace_final.append({
                    "pc": dut_trace["fetches"][fetches_index][0],
                    "instr": dut_trace["fetches"][fetches_index][1],
                    "target_reg": None,
                    "reg_val": None,
                    "mem_addr": None,
                    "mem_val": None,
                    "speculative_fetch": False,
                    "speculative_commit": speculative_commit
                })
                fetches_index += 1
                spike_index += 1
            elif is_reg_instruction(dut_trace["fetches"][fetches_index][1]):
                if write_to_zero: # just the fetch
                    dut_trace_final.append({
                        "pc": dut_trace["fetches"][fetches_index][0],
                        "instr": dut_trace["fetches"][fetches_index][1],
                        "target_reg": None,
                        "reg_val": None,
                        "mem_addr": None,
                        "mem_val": None,
                        "speculative_fetch": False,
                        "speculative_commit": speculative_commit
                    })
                    fetches_index += 1
                    spike_index += 1
                else:
                    if regfile_commits_index >= len(dut_trace["regfile_commits"]):
                        print(f"{elf_name} trace ended before expected (out of regfile_commits).")
                        break

                    reorder_superscalar_commits(spike_entry, dut_trace["regfile_commits"], regfile_commits_index)

                    dut_trace_final.append({
                        "pc": dut_trace["fetches"][fetches_index][0],
                        "instr": dut_trace["fetches"][fetches_index][1],
                        "target_reg": dut_trace["regfile_commits"][regfile_commits_index][0],
                        "reg_val": dut_trace["regfile_commits"][regfile_commits_index][1],
                        "mem_addr": None,
                        "mem_val": None,
                        "speculative_fetch": False,
                        "speculative_commit": speculative_commit
                    })
                    fetches_index += 1
                    regfile_commits_index += 1
                    spike_index += 1
                    spike_regfile[spike_entry["target_reg"]] = spike_entry["reg_val"]
                    
            elif is_jump_instruction(dut_trace["fetches"][fetches_index][1]):
                if write_to_zero: # just the fetch
                    dut_trace_final.append({
                        "pc": dut_trace["fetches"][fetches_index][0],
                        "instr": dut_trace["fetches"][fetches_index][1],
                        "target_reg": None,
                        "reg_val": None,
                        "mem_addr": None,
                        "mem_val": None,
                        "speculative_fetch": False,
                        "speculative_commit": speculative_commit
                    })
                    fetches_index += 1
                    spike_index += 1
                else:
                    if regfile_commits_index >= len(dut_trace["regfile_commits"]):
                        print(f"{elf_name} trace ended before expected (out of regfile_commits).")
                        break
                    
                    dut_trace_final.append({
                        "pc": dut_trace["fetches"][fetches_index][0],
                        "instr": dut_trace["fetches"][fetches_index][1],
                        "target_reg": dut_trace["regfile_commits"][regfile_commits_index][0],
                        "reg_val": dut_trace["regfile_commits"][regfile_commits_index][1],
                        "mem_addr": None,
                        "mem_val": None,
                        "speculative_fetch": False,
                        "speculative_commit": speculative_commit
                    })
                    fetches_index += 1
                    regfile_commits_index += 1
                    spike_index += 1
                    spike_regfile[spike_entry["target_reg"]] = spike_entry["reg_val"]

            elif is_fence_instruction(dut_trace["fetches"][fetches_index][1]):
                dut_trace_final.append({
                    "pc": dut_trace["fetches"][fetches_index][0],
                    "instr": dut_trace["fetches"][fetches_index][1],
                    "target_reg": None,
                    "reg_val": None,
                    "mem_addr": None,
                    "mem_val": None,
                    "speculative_fetch": False,
                    "speculative_commit": speculative_commit
                })
                fetches_index += 1
                spike_index += 1
            else:
                print(f"Unknown instruction: {hex(dut_trace['fetches'][fetches_index][1])}.")
                # ignore unknown instruction as a speculative fetch
                dut_trace_final.append({
                    "pc": dut_trace["fetches"][fetches_index][0],
                    "instr": dut_trace["fetches"][fetches_index][1],
                    "target_reg": None,
                    "reg_val": None,
                    "mem_addr": None,
                    "mem_val": None,
                    "speculative_fetch": True,
                    "speculative_commit": False
                })
                fetches_index += 1
                spike_index += 1
    return dut_trace_final

def compare_traces(spike_trace, dut_final_trace, elf_name):
    """
    Compare spike trace with dut final trace.
    Ignore speculative fetch entries in the dut final trace.
    """
    non_speculative_entries = [entry for entry in dut_final_trace if not entry.get("speculative_fetch", False)]
    mismatches = []
    
    for i in range(len(spike_trace)):
        spike_entry = spike_trace[i]

        if i >= len(non_speculative_entries):
            print(f"Comparison of {elf_name} ended before expected (out of dut entries).")
            empty_entry = {
                "pc": None,
                "instr": None,
                "target_reg": None,
                "reg_val": None,
                "mem_addr": None,
                "mem_val": None
            }
            mismatches.append({"spike": spike_entry,
                               "dut": empty_entry})
            break

        # DUT final trace does not show memory address for load instructions
        if spike_entry["instr"] & 0b1111111 == 0b0000011:
            dut_entry["mem_addr"] = None

        # align memory addresses to word boundaries for stores
        if WORD_BOUNDARY_STORES:
            if spike_entry["instr"] & 0b1111111 == 0b0100011:
                spike_entry["mem_addr"] = spike_entry["mem_addr"] & ~0b11

        dut_entry = non_speculative_entries[i].copy()
        dut_entry.pop("speculative_fetch", None)  # Remove speculative key if exists
        dut_entry.pop("speculative_commit", None)

        # Compare the spike entry with the DUT entry
        if spike_entry != dut_entry:
            mismatches.append({
                "spike": spike_entry,
                "dut": dut_entry
            })
    
    return mismatches

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Generate a final DUT trace and then compare it to spike's trace")
    
    # Create mutually exclusive groups
    group1 = parser.add_mutually_exclusive_group(required=True)
    group1.add_argument("--spike-trace", "-s", type=str, help="Path to the Spike trace file (lowercase mode)")
    group1.add_argument("--spike-trace-dir", "-S", type=str, help="Path to the Spike trace folder (uppercase mode)")
    
    group2 = parser.add_mutually_exclusive_group(required=True)
    group2.add_argument("--dut-trace", "-d", type=str, help="Path to the DUT's fragmented trace file (lowercase mode)")
    group2.add_argument("--dut-trace-dir", "-D", type=str, help="Path to the DUT's fragmented trace file (uppercase mode)")
    
    parser.add_argument("--output-folder", "-o", type=str, required=False, help="Folder to save the final speculative DUT trace")
    args = parser.parse_args()
    
    # Validate that both arguments are from the same group (both lowercase or both uppercase)
    lowercase_used = args.spike_trace is not None and args.dut_trace is not None
    uppercase_used = args.spike_trace_dir is not None and args.dut_trace_dir is not None

    if not (lowercase_used or uppercase_used):
        parser.error("You must use either both lowercase options for single file (-s and -d) or both uppercase options for folders (-S and -D)")
    
    if lowercase_used:
        with open(args.spike_trace, "r") as f:
            spike_trace = json.load(f)
        with open(args.dut_trace, "r") as f:
            dut_trace = json.load(f)

        basename = os.path.basename(args.spike_trace)
        elf_name = basename.split(".")[0]
        dut_final_trace = generate_final_trace(spike_trace, dut_trace, elf_name)

        basename = os.path.basename(args.spike_trace)
        elf_name = basename.split(".")[0]
        with open(f"{args.output_folder}/{elf_name}.final.json", "w") as f:
            json.dump(dut_final_trace, f, indent=2)

        mismatches = compare_traces(spike_trace, dut_final_trace, elf_name)

        if mismatches:
            print(f"\033[91mMismatches found for {elf_name}:\033[0m")
            for mismatch in mismatches:
                
                # Format spike entry with hex values
                spike_formatted = mismatch["spike"].copy()
                if spike_formatted["pc"] is not None:
                    spike_formatted["pc"] = f"0x{spike_formatted['pc']:08x}"
                if spike_formatted["instr"] is not None:
                    spike_formatted["instr"] = f"0x{spike_formatted['instr']:08x}"
                if spike_formatted["reg_val"] is not None:
                    spike_formatted["reg_val"] = f"0x{spike_formatted['reg_val']:08x}"
                if spike_formatted["mem_addr"] is not None:
                    spike_formatted["mem_addr"] = f"0x{spike_formatted['mem_addr']:08x}"
                if spike_formatted["mem_val"] is not None:
                    spike_formatted["mem_val"] = f"0x{spike_formatted['mem_val']:08x}"
                
                # Format DUT entry with hex values
                dut_formatted = mismatch["dut"].copy()
                if dut_formatted["pc"] is not None:
                    dut_formatted["pc"] = f"0x{dut_formatted['pc']:08x}"
                if dut_formatted["instr"] is not None:
                    dut_formatted["instr"] = f"0x{dut_formatted['instr']:08x}"
                if dut_formatted["reg_val"] is not None:
                    dut_formatted["reg_val"] = f"0x{dut_formatted['reg_val']:08x}"
                if dut_formatted["mem_addr"] is not None:
                    dut_formatted["mem_addr"] = f"0x{dut_formatted['mem_addr']:08x}"
                if dut_formatted["mem_val"] is not None:
                    dut_formatted["mem_val"] = f"0x{dut_formatted['mem_val']:08x}"
                
                print("Spike entry:\t", spike_formatted)
                print("DUT entry:\t", dut_formatted)
                print()
            
        else:
            print("\033[92mNo mismatches found for", elf_name, "\033[0m")
            
    else:
        spike_files = sorted(os.listdir(args.spike_trace_dir))
        if not spike_files:
            print(f"No files found in spike trace directory: {args.spike_trace_dir}")
            exit(1)
        
        for spike_file in spike_files:
            if spike_file.endswith(".spike.json"):
                elf_name = spike_file.split(".")[0]
                spike_path = os.path.join(args.spike_trace_dir, spike_file)
                dut_path = os.path.join(args.dut_trace_dir, f"{elf_name}.fragmented.json")
                if not os.path.exists(dut_path):
                    print(f"DUT trace file not found: {dut_path}")
                    continue

                with open(spike_path, "r") as f:
                    spike_trace = json.load(f)
                with open(dut_path, "r") as f:
                    dut_trace = json.load(f)
                
                dut_final_trace = generate_final_trace(spike_trace, dut_trace, elf_name)

                with open(f"{args.output_folder}/{elf_name}.final.json", "w") as f:
                    json.dump(dut_final_trace, f, indent=2)

                mismatches = compare_traces(spike_trace, dut_final_trace, elf_name)

                if mismatches:
                    print(f"\033[91mMismatches found for {elf_name}:\033[0m")
                    for mismatch in mismatches:
                        
                        # Format spike entry with hex values
                        spike_formatted = mismatch["spike"].copy()
                        if spike_formatted["pc"] is not None:
                            spike_formatted["pc"] = f"0x{spike_formatted['pc']:08x}"
                        if spike_formatted["instr"] is not None:
                            spike_formatted["instr"] = f"0x{spike_formatted['instr']:08x}"
                        if spike_formatted["reg_val"] is not None:
                            spike_formatted["reg_val"] = f"0x{spike_formatted['reg_val']:08x}"
                        if spike_formatted["mem_addr"] is not None:
                            spike_formatted["mem_addr"] = f"0x{spike_formatted['mem_addr']:08x}"
                        if spike_formatted["mem_val"] is not None:
                            spike_formatted["mem_val"] = f"0x{spike_formatted['mem_val']:08x}"
                        
                        # Format DUT entry with hex values
                        dut_formatted = mismatch["dut"].copy()
                        if dut_formatted["pc"] is not None:
                            dut_formatted["pc"] = f"0x{dut_formatted['pc']:08x}"
                        if dut_formatted["instr"] is not None:
                            dut_formatted["instr"] = f"0x{dut_formatted['instr']:08x}"
                        if dut_formatted["reg_val"] is not None:
                            dut_formatted["reg_val"] = f"0x{dut_formatted['reg_val']:08x}"
                        if dut_formatted["mem_addr"] is not None:
                            dut_formatted["mem_addr"] = f"0x{dut_formatted['mem_addr']:08x}"
                        if dut_formatted["mem_val"] is not None:
                            dut_formatted["mem_val"] = f"0x{dut_formatted['mem_val']:08x}"
                        
                        print("Spike entry:\t", spike_formatted)
                        print("DUT entry:\t", dut_formatted)
                        print()
                
                else:
                    print("\033[92mNo mismatches found for", elf_name, "\033[0m")

