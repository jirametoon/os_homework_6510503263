#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copy-on-Write (CoW) demonstration in Python
Student: จิรเมธ วัฒนไพบูลย์ (6510503263)
Platform: Linux only (uses /proc and os.fork)
Safety: Limits allocation sizes and minimizes memory pressure

This program:
- Allocates a large bytearray (default sizes: 50, 75, 100 MB)
- Touches one byte per page to commit memory
- fork() into parent/child and observes VmRSS from /proc/self/status
- Child modifies one byte per page to trigger CoW; observe RSS change
- Repeats for different sizes

Do NOT run on Windows. Run on Linux only.
"""
from __future__ import annotations
import argparse
import os
import sys
import time
from typing import List


def get_rss_kb() -> int:
    """Read VmRSS from /proc/self/status (Linux only)."""
    try:
        with open('/proc/self/status', 'r') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    # e.g., 'VmRSS:\t  12345 kB\n'
                    parts = ''.join(ch if ch.isdigit() else ' ' for ch in line)
                    nums = parts.split()
                    if nums:
                        return int(nums[0])
    except Exception:
        return 0
    return 0


def touch_memory(buf: bytearray, page: int) -> None:
    """Write one byte per page to commit pages in RAM."""
    n = len(buf)
    for i in range(0, n, page):
        buf[i] = (i // page) & 0xFF
    if n > 0:
        buf[-1] = 0xAA


def modify_memory_xor(buf: bytearray, page: int) -> None:
    """Modify one byte per page (forces CoW when child writes)."""
    n = len(buf)
    for i in range(0, n, page):
        buf[i] ^= 0xFF
    if n > 0:
        buf[-1] ^= 0x55


def print_status(role: str, pid: int, size_mb: int, phase: str) -> None:
    rss = get_rss_kb()
    print(f"[{role}][pid={pid}][size={size_mb} MB] {phase}: VmRSS={rss} kB")
    sys.stdout.flush()


def parse_sizes_arg(arg: str) -> List[int]:
    out: List[int] = []
    for part in arg.split(','):
        part = part.strip()
        if not part:
            continue
        v = int(part)
        if v <= 0:
            raise ValueError('sizes must be positive integers')
        out.append(v)
    if not out:
        raise ValueError('no sizes parsed')
    return out


def run_trial(size_mb: int) -> int:
    page = os.sysconf('SC_PAGESIZE')
    max_mb = 256  # safety cap
    if size_mb < 10 or size_mb > max_mb:
        print(f"Refusing size {size_mb} MB (allowed: 10-{max_mb} MB)")
        return -1

    bytes_n = size_mb * 1024 * 1024
    print(f"\n=== Trial: size={size_mb} MB ({bytes_n / page:.2f} pages) ===")

    try:
        buf = bytearray(bytes_n)
    except MemoryError:
        print("MemoryError: allocation failed")
        return -1

    # Commit pages and measure
    touch_memory(buf, page)
    print_status('parent', os.getpid(), size_mb, 'after-initialize-before-fork')

    # Pipes for sync: parent->child (p2c), child->parent (c2p)
    p2c_r, p2c_w = os.pipe()
    c2p_r, c2p_w = os.pipe()

    pid = os.fork()
    if pid == 0:
        # Child
        try:
            os.close(p2c_w)
            os.close(c2p_r)
            print_status('child', os.getpid(), size_mb, 'just-after-fork')
            # Notify parent ready
            os.write(c2p_w, b'R')
            # Wait for go
            os.read(p2c_r, 1)
            # Modify to trigger CoW
            modify_memory_xor(buf, page)
            print_status('child', os.getpid(), size_mb, 'after-child-modify')
            # Done
            os.write(c2p_w, b'D')
        finally:
            try:
                os.close(p2c_r)
            except OSError:
                pass
            try:
                os.close(c2p_w)
            except OSError:
                pass
            os._exit(0)
    else:
        # Parent
        os.close(p2c_r)
        os.close(c2p_w)
        print_status('parent', os.getpid(), size_mb, 'just-after-fork')
        # Wait for child ready
        os.read(c2p_r, 1)
        # Tell child to start modify
        os.write(p2c_w, b'G')
        # Wait for child done
        os.read(c2p_r, 1)
        # Measure after child modified
        print_status('parent', os.getpid(), size_mb, 'after-child-modify')
        # Cleanup
        try:
            os.close(p2c_w)
        except OSError:
            pass
        try:
            os.close(c2p_r)
        except OSError:
            pass
        # Wait child
        os.waitpid(pid, 0)
    return 0


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description='Copy-on-Write (CoW) demo (Linux only)')
    parser.add_argument('--sizes', type=str, default='50,75,100', help='Comma-separated MB sizes, default: 50,75,100')
    args = parser.parse_args(argv)

    try:
        sizes = parse_sizes_arg(args.sizes)
    except Exception as e:
        print(f"Invalid --sizes: {e}")
        return 2

    print(f"CoW demo starting (pid={os.getpid()}). Page size={os.sysconf('SC_PAGESIZE')} bytes.")
    print("NOTE: Run on Linux only. This program reads /proc to observe VmRSS.")

    for sz in sizes:
        if run_trial(sz) != 0:
            print(f"Trial with {sz} MB failed or skipped.")

    print("\nAll trials completed.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
