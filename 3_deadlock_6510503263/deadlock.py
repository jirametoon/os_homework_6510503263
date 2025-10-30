#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deadlock Avoidance, Detection, and Resolution demo (Linux-safe, simulation only)
Student: จิรเมธ วัฒนไพบูลย์ (6510503263)

- Simulated resources only (no real OS resources are locked)
- Threads represent processes; safe for DO NO HARM
- Modes:
  * avoidance: use Banker's Algorithm, no deadlock occurs
  * detection: naive allocation with waiting; detect deadlock via wait-for graph and resolve by aborting victims

Run examples (Linux, do not run on Windows):
  python3 deadlock.py --mode avoidance
  python3 deadlock.py --mode detection
  python3 deadlock.py --mode detection --seed 42 --n 5 --resources 3,3,2
"""
from __future__ import annotations
import argparse
import random
import threading
import time
from typing import List, Dict, Tuple, Optional

# --------------------------- Utilities ---------------------------

def parse_int_list(s: str) -> List[int]:
    return [int(x.strip()) for x in s.split(',') if x.strip()]

# --------------------------- Resource Manager ---------------------------

class ResourceManager:
    """
    Manages simulated resources.
    Supports:
     - Banker's algorithm for avoidance (safe granting)
     - Naive blocking allocation for detection mode
     - Wait-for graph construction and cycle detection
     - Deadlock resolution by aborting victim threads
    """
    def __init__(self, total: List[int], max_demand: List[List[int]], mode: str = 'avoidance'):
        self.m = len(total)             # number of resource types
        self.n = len(max_demand)        # number of processes
        self.total = total[:]           # total units per resource type
        self.available = total[:]       # available units
        self.max = [row[:] for row in max_demand]
        self.alloc = [[0]*self.m for _ in range(self.n)]
        self.need = [[self.max[i][k] - self.alloc[i][k] for k in range(self.m)] for i in range(self.n)]

        self.mode = mode
        self.lock = threading.RLock()
        self.cv = threading.Condition(self.lock)
        self.alive = [True]*self.n   # marks process alive; set False when aborted
        self.finished = [False]*self.n

    # ------------- Common helpers -------------
    def _can_grant(self, i: int, req: List[int]) -> bool:
        return all(0 <= req[k] <= self.available[k] for k in range(self.m))

    def _apply_grant(self, i: int, req: List[int]) -> None:
        for k in range(self.m):
            self.available[k] -= req[k]
            self.alloc[i][k] += req[k]
            self.need[i][k] -= req[k]

    def _undo_grant(self, i: int, req: List[int]) -> None:
        for k in range(self.m):
            self.available[k] += req[k]
            self.alloc[i][k] -= req[k]
            self.need[i][k] += req[k]

    def _release_all(self, i: int) -> List[int]:
        rel = [0]*self.m
        for k in range(self.m):
            rel[k] = self.alloc[i][k]
            self.available[k] += self.alloc[i][k]
            self.alloc[i][k] = 0
            # self.need[i][k] stays as max - alloc => becomes max[i][k]
            self.need[i][k] = self.max[i][k]
        return rel

    # ------------- Banker's Algorithm -------------
    def _is_safe_after_grant(self, i: int, req: List[int]) -> bool:
        # Work = available - req; Need and Alloc adjusted for i
        work = [self.available[k] - req[k] for k in range(self.m)]
        alloc = [row[:] for row in self.alloc]
        need = [row[:] for row in self.need]
        for k in range(self.m):
            alloc[i][k] += req[k]
            need[i][k] -= req[k]

        finish = [self.finished[j] or not self.alive[j] for j in range(self.n)]
        progress = True
        while progress:
            progress = False
            for j in range(self.n):
                if not finish[j]:
                    if all(need[j][k] <= work[k] for k in range(self.m)):
                        # pretend j can finish
                        for k in range(self.m):
                            work[k] += alloc[j][k]
                        finish[j] = True
                        progress = True
        return all(finish[j] for j in range(self.n))

    # ------------- Public API for worker threads -------------
    def request(self, i: int, req: List[int], timeout: Optional[float] = None) -> bool:
        """Attempt to request resources for process i.
        Returns True if granted, False if timed out or aborted.
        In avoidance mode: use Banker's algorithm; in detection mode: naive grant if available else wait.
        """
        with self.cv:
            # basic validity: req <= need and non-negative
            if any(req[k] < 0 or req[k] > self.need[i][k] for k in range(self.m)):
                print(f"[proc {i}] invalid request {req}, need={self.need[i]}")
                return False

            start = time.time()
            while self.alive[i] and not self.finished[i]:
                if self.mode == 'avoidance':
                    if self._can_grant(i, req) and self._is_safe_after_grant(i, req):
                        self._apply_grant(i, req)
                        print(f"[avoid][grant] proc {i} req={req} alloc={self.alloc[i]} avail={self.available}")
                        return True
                    else:
                        # wait until resources available or state changes
                        print(f"[avoid][wait ] proc {i} req={req} need={self.need[i]} avail={self.available}")
                else:  # detection mode
                    if self._can_grant(i, req):
                        self._apply_grant(i, req)
                        print(f"[detect][grant] proc {i} req={req} alloc={self.alloc[i]} avail={self.available}")
                        return True
                    else:
                        print(f"[detect][block] proc {i} req={req} need={self.need[i]} avail={self.available}")

                if timeout is not None:
                    remaining = max(0.0, timeout - (time.time() - start))
                    if remaining == 0.0:
                        return False
                    self.cv.wait(timeout=remaining)
                else:
                    self.cv.wait()

            return False  # aborted or finished

    def release_all(self, i: int) -> None:
        with self.cv:
            rel = self._release_all(i)
            print(f"[proc {i}] release_all={rel} avail={self.available}")
            self.cv.notify_all()

    def mark_finished(self, i: int) -> None:
        with self.cv:
            self.finished[i] = True
            self.cv.notify_all()

    def abort(self, i: int) -> None:
        with self.cv:
            if not self.alive[i]:
                return
            self.alive[i] = False
            rel = self._release_all(i)
            print(f"[resolve] abort proc {i} -> released {rel}, avail={self.available}")
            self.cv.notify_all()

    # ------------- Detection via Wait-For Graph -------------
    def build_wait_for_graph(self, waiting: Dict[int, List[int]]) -> Dict[int, List[int]]:
        """Build wait-for graph: edge i->j if i waits on resources held by j.
        waiting: processes currently waiting and their outstanding request vectors.
        """
        graph: Dict[int, List[int]] = {i: [] for i in range(self.n)}
        with self.lock:
            for i, req in waiting.items():
                if not self.alive[i] or self.finished[i]:
                    continue
                # For each resource type k where req[k] > available[k], find holders j
                for k in range(self.m):
                    if req[k] > self.available[k]:
                        for j in range(self.n):
                            if i != j and self.alloc[j][k] > 0 and self.alive[j] and not self.finished[j]:
                                if j not in graph[i]:
                                    graph[i].append(j)
        return graph

    @staticmethod
    def find_cycle(graph: Dict[int, List[int]]) -> Optional[List[int]]:
        """Return one cycle as list of nodes if exists, else None."""
        color: Dict[int, int] = {u: 0 for u in graph}  # 0=unvisited,1=visiting,2=done
        stack: List[int] = []

        def dfs(u: int) -> Optional[List[int]]:
            color[u] = 1
            stack.append(u)
            for v in graph.get(u, []):
                if color[v] == 0:
                    cyc = dfs(v)
                    if cyc is not None:
                        return cyc
                elif color[v] == 1:
                    # found back-edge; extract cycle
                    if v in stack:
                        idx = stack.index(v)
                        return stack[idx:] + [v]
            stack.pop()
            color[u] = 2
            return None

        for u in graph:
            if color[u] == 0:
                cyc = dfs(u)
                if cyc is not None:
                    return cyc
        return None

# --------------------------- Worker threads ---------------------------

def bounded_random_request(need: List[int], max_per_step: int = 2) -> List[int]:
    # Generate a small request up to need, capped per step
    req = []
    for k in range(len(need)):
        cap = min(need[k], max_per_step)
        req.append(random.randint(0, cap) if cap > 0 else 0)
    if all(x == 0 for x in req) and any(n > 0 for n in need):
        # ensure progress if need remains
        k = random.choice([i for i, n in enumerate(need) if n > 0])
        req[k] = 1
    return req


def worker(i: int, rm: ResourceManager, waiting_map: Dict[int, List[int]], mode: str,
           think_time: Tuple[float, float] = (0.02, 0.06)) -> None:
    random_sleep = lambda: time.sleep(random.uniform(*think_time))

    while True:
        with rm.lock:
            if not rm.alive[i]:
                print(f"[proc {i}] aborted, exiting")
                return
            if rm.finished[i]:
                return
            need = rm.need[i][:]
        if all(x == 0 for x in need):
            # done, release all and finish
            rm.mark_finished(i)
            rm.release_all(i)
            print(f"[proc {i}] finished")
            return

        req = bounded_random_request(need)
        # Attempt to request
        granted = rm.request(i, req, timeout=0.2 if mode == 'detection' else 0.5)
        if not granted:
            if mode == 'detection':
                # mark as waiting for detection thread to observe
                with rm.lock:
                    waiting_map[i] = req
            # back off a bit
            random_sleep()
        else:
            # clear waiting status
            with rm.lock:
                waiting_map.pop(i, None)
            random_sleep()

# --------------------------- Detector/Resolver thread ---------------------------

def detector_loop(rm: ResourceManager, waiting_map: Dict[int, List[int]],
                  interval: float = 0.5, max_iterations: int = 200) -> None:
    """Periodically build WFG, detect cycles, and resolve by aborting a victim."""
    iters = 0
    while iters < max_iterations:
        time.sleep(interval)
        iters += 1

        # Check if all finished or dead
        with rm.lock:
            if all(rm.finished[i] or not rm.alive[i] for i in range(rm.n)):
                return

        graph = rm.build_wait_for_graph(dict(waiting_map))
        cyc = rm.find_cycle(graph)
        if cyc:
            # choose a victim: process with largest total allocation within the cycle
            victims = cyc[:-1]  # last equals first; drop duplicate
            with rm.lock:
                alloc_sums = {i: sum(rm.alloc[i]) for i in victims}
            victim = max(victims, key=lambda x: alloc_sums.get(x, 0))
            print(f"[detect] Deadlock cycle found: {cyc}. Aborting victim proc {victim}")
            rm.abort(victim)

# --------------------------- Scenario setup ---------------------------

def generate_max_demand(n: int, m: int, total: List[int]) -> List[List[int]]:
    max_list: List[List[int]] = []
    for _ in range(n):
        row = []
        for k in range(m):
            # each process maximum need is between 0 and total[k]
            row.append(random.randint(0, max(0, total[k])))
        if all(x == 0 for x in row):
            # ensure some demand
            row[random.randrange(m)] = 1
        max_list.append(row)
    return max_list


def main():
    parser = argparse.ArgumentParser(description='Deadlock Avoidance/Detection/Resolution Demo (Simulated)')
    parser.add_argument('--mode', choices=['avoidance', 'detection'], default='avoidance',
                        help='avoidance=Banker\'s Algorithm (no deadlock), detection=detect & resolve deadlock')
    parser.add_argument('--resources', type=str, default='3,3,2', help='Total resources per type, e.g., 3,3,2')
    parser.add_argument('--n', type=int, default=5, help='Number of processes (threads)')
    parser.add_argument('--seed', type=int, default=123, help='Random seed for reproducibility')
    args = parser.parse_args()

    random.seed(args.seed)
    total = parse_int_list(args.resources)
    m = len(total)
    n = args.n

    # Generate maximum demand matrix
    max_demand = generate_max_demand(n, m, total)

    print(f"Mode={args.mode} total={total} n={n}")
    print("Max demand per process:")
    for i, row in enumerate(max_demand):
        print(f"  P{i}: {row}")

    rm = ResourceManager(total=total, max_demand=max_demand, mode=args.mode)
    waiting_map: Dict[int, List[int]] = {}

    # Start workers
    threads = []
    for i in range(n):
        t = threading.Thread(target=worker, args=(i, rm, waiting_map, args.mode), name=f"P{i}")
        t.daemon = True
        threads.append(t)
        t.start()

    # Start detector only for detection mode
    det = None
    if args.mode == 'detection':
        det = threading.Thread(target=detector_loop, args=(rm, waiting_map), name='detector')
        det.daemon = True
        det.start()

    # Join workers
    for t in threads:
        t.join(timeout=30.0)

    # Final resolution pass if needed
    if args.mode == 'detection':
        with rm.lock:
            unfinished = [i for i in range(n) if rm.alive[i] and not rm.finished[i]]
        if unfinished:
            print(f"[final] Forcing abort of remaining: {unfinished}")
            for i in unfinished:
                rm.abort(i)
        if det is not None:
            det.join(timeout=2.0)

    print("All done.")


if __name__ == '__main__':
    main()
