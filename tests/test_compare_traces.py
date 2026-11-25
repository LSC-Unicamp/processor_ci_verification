import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compare_traces import compare_traces, generate_final_trace, is_reg_instruction


def test_csr_register_write_is_not_discarded_as_unknown_instruction():
    instruction = 0x30002373  # csrr x6, mstatus
    assert is_reg_instruction(instruction)
    spike = [{"pc": 0, "instr": instruction, "target_reg": 6, "reg_val": 7,
              "mem_addr": None, "mem_val": None}]
    dut = {"fetches": [[0, instruction]], "regfile_commits": [[6, 7]],
           "memory_accesses": []}
    assert compare_traces(spike, generate_final_trace(spike, dut, "probe"), "probe") == []


def test_comparison_normalizes_fetch_flag_and_load_address():
    spike = [{"pc": 4, "instr": 0x00002283, "target_reg": 5, "reg_val": 9,
              "mem_addr": 0x100, "mem_val": None}]
    final = [{"pc": 5, "instr": 0x00002283, "target_reg": 5, "reg_val": 9,
              "mem_addr": None, "mem_val": None, "speculative_fetch": False,
              "speculative_commit": False}]
    assert compare_traces(spike, final, "probe") == []


def test_byte_store_accepts_word_or_byte_addressed_wrapper_bus():
    instruction = 0x005100a3  # sb x5, 1(x2)
    spike = [{"pc": 0, "instr": instruction, "target_reg": None, "reg_val": None,
              "mem_addr": 0x101, "mem_val": 0x12}]
    for bus_address in (0x100, 0x101):
        dut = {"fetches": [[0, instruction]], "regfile_commits": [],
               "memory_accesses": [[bus_address, 0x1200]]}
        final = generate_final_trace(spike, dut, "probe")
        assert compare_traces(spike, final, "probe") == []
