gcc -O2 -Wall -Wextra -std=c11 -o cow cow.c
# RUN (Linux only; Python)

This program demonstrates Copy-on-Write (CoW) after `fork()` by observing each process's Resident Set Size (VmRSS) from `/proc/self/status`.

Important
- Linux only. It uses `/proc` and `os.fork()`.
- DO NO HARM: default sizes are modest (50, 75, 100 MB). A safety cap prevents sizes over 256 MB per trial.
- Run on a machine where you have permission and understand memory usage. Avoid running on production systems.

## Requirements
- Python 3.8+

## Run
Default sizes (MB) are 50, 75, 100.
```bash
python3 cow.py
```

Specify sizes explicitly (MB, comma-separated):
```bash
python3 cow.py --sizes 50,100
python3 cow.py --sizes 50,75,100
```

### Example output (illustrative only)
```
CoW demo starting (pid=12345). Page size=4096 bytes.
NOTE: Run on Linux only. This program reads /proc to observe VmRSS.

=== Trial: size=50 MB (12800.00 pages) ===
[parent][pid=12345][size=50 MB] after-initialize-before-fork: VmRSS=52000 kB
[parent][pid=12345][size=50 MB] just-after-fork: VmRSS=52000 kB
[child][pid=12346][size=50 MB] just-after-fork: VmRSS=52000 kB
[child][pid=12346][size=50 MB] after-child-modify: VmRSS=78000 kB
[parent][pid=12345][size=50 MB] after-child-modify: VmRSS=52000 kB
```
Interpretation:
- Right after fork, both parent and child report similar VmRSS (pages are shared via CoW).
- After the child writes, its VmRSS increases (private copies are created). The parent's VmRSS remains about the same.

## Notes
- VmRSS counts shared pages per-process; system-wide memory is not doubled until pages are written and become private. For deeper analysis, consider inspecting `/proc/<pid>/smaps_rollup` fields (Shared_Clean, Private_Dirty), but this program keeps to VmRSS for clarity.
- The program synchronizes parent/child with pipes so that the measurement order is deterministic.
- If allocation fails, the trial is skipped.
