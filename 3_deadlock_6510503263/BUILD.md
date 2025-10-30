# BUILD and RUN (Linux only)

This is a safe, simulated demo of deadlock avoidance, detection, and resolution. It uses Python threads to represent processes and simulated resources only. No real system resources are locked.

Important
- Linux only, as per assignment constraint. Do NOT run on production systems.
- DO NO HARM: uses small, in-memory simulation and short sleeps; no heavy resource usage.

## Requirements
- Python 3.8+

## Run
Avoidance mode (Banker’s Algorithm): no deadlock occurs; all finish.
```bash
python3 deadlock.py --mode avoidance
```

Detection mode: naive blocking; a detector finds a cycle in the wait-for graph and resolves by aborting a victim.
```bash
python3 deadlock.py --mode detection
```

Options
- `--resources 3,3,2`  total resources per type (comma-separated)
- `--n 5`              number of processes (threads)
- `--seed 123`         random seed for reproducibility

Examples
```bash
python3 deadlock.py --mode avoidance --resources 3,3,2 --n 5 --seed 123
python3 deadlock.py --mode detection --resources 3,3,2 --n 5 --seed 42
```

### Expected console highlights
- Avoidance: lines with `[avoid][grant]` and possibly `[avoid][wait ]`, finishing without deadlock.
- Detection: lines with `[detect][block]`, a printed "Deadlock cycle found:" and "[resolve] abort proc ...", then progress resumes.

Notes
- The simulation constructs a wait-for graph (WFG) from current waiting requests and existing allocations, then uses DFS to find a cycle.
- Resolution policy aborts one process in the cycle (largest allocation) and releases its resources, allowing others to proceed.
