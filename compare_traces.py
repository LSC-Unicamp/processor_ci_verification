import argparse
import json
import os

def is_load_instruction(instruction):
    load_op_code = instruction & 0b1111111 == 0b0000011 # lb, lh, lw, lbu, lhu
    return load_op_code
    
def is_store_instruction(instruction):
    store_op_code = instruction & 0b1111111 == 0b0100011 # sb, sh, sw
    return store_op_code

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

def generate_final_trace(spike_trace, dut_trace):
    """
    Compare two execution traces, but the spike_trace is different than the dut trace.
    DUT trace is composed of trace fragments, and then a speculative trace is created.
    """

    # Generate processor/dut trace while comparing to the spike trace
    fetches_index = 0
    regfile_commits_index = 0
    memory_accesses_index = 0
    dut_trace_final = []
    for spike_entry in spike_trace:
        
        # dut_trace was shorter than spike_trace, probably a bug
        if fetches_index >= len(dut_trace["fetches"]):
            print("Trace ended before expected (out of fetches).")
            break

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
                "speculative": True
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
                        "speculative": False
                    })
                    fetches_index += 1
                else:
                    if regfile_commits_index >= len(dut_trace["regfile_commits"]):
                        print("Trace ended before expected (out of regfile_commits).")
                        break

                    dut_trace_final.append({
                        "pc": dut_trace["fetches"][fetches_index][0],
                        "instr": dut_trace["fetches"][fetches_index][1],
                        "target_reg": dut_trace["regfile_commits"][regfile_commits_index][0],
                        "reg_val": dut_trace["regfile_commits"][regfile_commits_index][1],
                        "mem_addr": None,
                        "mem_val": None,
                        "speculative": False
                    })
                    fetches_index += 1
                    regfile_commits_index += 1

            elif is_store_instruction(dut_trace["fetches"][fetches_index][1]):
                if memory_accesses_index >= len(dut_trace["memory_accesses"]):
                    print("Trace ended before expected (out of memory accesses)")
                    break
                
                dut_trace_final.append({
                    "pc": dut_trace["fetches"][fetches_index][0],
                    "instr": dut_trace["fetches"][fetches_index][1],
                    "target_reg": None,
                    "reg_val": None,
                    "mem_addr": dut_trace["memory_accesses"][memory_accesses_index][0],
                    "mem_val": dut_trace["memory_accesses"][memory_accesses_index][1],
                    "speculative": False
                })
                fetches_index += 1
                memory_accesses_index += 1
            elif is_branch_instruction(dut_trace["fetches"][fetches_index][1]):
                dut_trace_final.append({
                    "pc": dut_trace["fetches"][fetches_index][0],
                    "instr": dut_trace["fetches"][fetches_index][1],
                    "target_reg": None,
                    "reg_val": None,
                    "mem_addr": None,
                    "mem_val": None,
                    "speculative": False
                })
                fetches_index += 1
            elif is_reg_instruction(dut_trace["fetches"][fetches_index][1]):
                if write_to_zero: # just the fetch
                    dut_trace_final.append({
                        "pc": dut_trace["fetches"][fetches_index][0],
                        "instr": dut_trace["fetches"][fetches_index][1],
                        "target_reg": None,
                        "reg_val": None,
                        "mem_addr": None,
                        "mem_val": None,
                        "speculative": False
                    })
                    fetches_index += 1
                else:
                    if regfile_commits_index >= len(dut_trace["regfile_commits"]):
                        print("Trace ended before expected (out of regfile_commits).")
                        break

                    dut_trace_final.append({
                        "pc": dut_trace["fetches"][fetches_index][0],
                        "instr": dut_trace["fetches"][fetches_index][1],
                        "target_reg": dut_trace["regfile_commits"][regfile_commits_index][0],
                        "reg_val": dut_trace["regfile_commits"][regfile_commits_index][1],
                        "mem_addr": None,
                        "mem_val": None,
                        "speculative": False
                    })
                    fetches_index += 1
                    regfile_commits_index += 1
            else:
                print(f"Unknown instruction: {dut_trace['fetches'][fetches_index][1]}.")
                # ignore unknown instruction as a speculative fetch
                dut_trace_final.append({
                    "pc": dut_trace["fetches"][fetches_index][0],
                    "instr": dut_trace["fetches"][fetches_index][1],
                    "target_reg": None,
                    "reg_val": None,
                    "mem_addr": None,
                    "mem_val": None,
                    "speculative": False
                })
                fetches_index += 1
    return dut_trace_final

def compare_traces(spike_trace, dut_final_trace):
    """
    Compare spike trace with dut final trace.
    Ignore speculative entries in the dut final trace.
    """
    non_speculative_entries = [entry for entry in dut_final_trace if not entry.get("speculative", False)]
    mismatches = []
    
    for i in range(len(spike_trace)):
        if i >= len(non_speculative_entries):
            print("DUT trace ended before expected (out of dut entries).")
            break

        spike_entry = spike_trace[i]
        # DUT final trace does not show memory address for load instructions
        if spike_entry["instr"] & 0b1111111 == 0b0000011:
            dut_entry["mem_addr"] = None

        dut_entry = non_speculative_entries[i].copy()
        dut_entry.pop("speculative", None)  # Remove speculative key if exists

        # Compare the spike entry with the DUT entry
        if spike_entry != dut_entry:
            mismatches.append({
                "spike": spike_entry,
                "dut": dut_entry
            })
    
    return mismatches

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a final DUT trace and then compare it to spike's trace")
    parser.add_argument("--spike-trace", "-s", type=str, required=True, help="Path to the Spike trace file")
    parser.add_argument("--dut-trace", "-d", type=str, required=True, help="Path to the DUT's fragmented trace file")
    parser.add_argument("--output-folder", "-o", type=str, required=False, help="Folder to save the final speculative DUT trace")
    args = parser.parse_args()

    with open(args.spike_trace, "r") as f:
        spike_trace = json.load(f)
    with open(args.dut_trace, "r") as f:
        dut_trace = json.load(f)
    dut_final_trace = generate_final_trace(spike_trace, dut_trace)

    with open(f"{args.output_folder}/{os.path.splitext(os.path.basename(args.spike_trace))[0]}.final.json", "w") as f:
        json.dump(dut_final_trace, f, indent=2)

    mismatches = compare_traces(spike_trace, dut_final_trace)

    basename = os.path.basename(args.spike_trace)
    elf_name = basename.split(".")[0]

    for mismatch in mismatches:
        print(f"\033[91mMismatch found for {elf_name}:\033[0m")
        print("Spike entry:\t", mismatch["spike"])
        print("DUT entry:\t", mismatch["dut"])
        print()
    
    if not mismatches:
        print("\033[92mNo mismatches found for", elf_name, "\033[0m")

