# ProcessorCI Verification Documentation

## NTV Responsibilities

This repository owns the trace-based verification flow:

- DUT trace capture through Cocotb simulation.
- Reference trace capture through the Spike fork.
- Trace reconstruction and comparison.
- Example assets that demonstrate the required makefile, wrapper, register-file,
  and flag inputs.

## File Boundaries

- Root Python scripts are the public command-line interface.
- `example/` is the smallest runnable reference for documentation and debugging.
- `spike_fork/` contains third-party/forked simulator code and should not be
  mixed with ProcessorCI scripts.
- Generated traces and comparison output should be written to an explicit output
  directory such as `output/`.

## Adding A Processor Example

Add or update:

- A Cocotb makefile for the processor.
- A wrapper/top file that exposes the monitored interfaces.
- A `*_reg_file.json` file with register-file labels.
- A `*_manual_ntv_flags.json` file when automatic behavior is insufficient.
- A README/example note showing the exact commands.

## Validation Checklist

For documentation changes, verify referenced paths with:

```bash
find example -maxdepth 2 -type f
python3 exec_trace.py --help
python3 spike_trace.py --help
python3 compare_traces.py --help
```

Full trace validation requires the simulator and Spike dependencies.
