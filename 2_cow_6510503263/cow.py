#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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

def read_smaps_rollup_kb(pid: int) -> dict:
    """
    อ่านค่า key สำคัญจาก /proc/<pid>/smaps_rollup (หน่วย kB)
    ใช้ได้บน Linux/WSL2 สำหรับโปรเซสของเราเอง
    """
    path = f"/proc/{pid}/smaps_rollup"
    fields = {
        "Rss": 0,
        "Pss": 0,
        "Shared_Clean": 0,
        "Shared_Dirty": 0,
        "Private_Clean": 0,
        "Private_Dirty": 0,
        "Referenced": 0,
        "Anonymous": 0,
        "AnonHugePages": 0,
    }
    try:
        with open(path, "r") as f:
            for line in f:
                if ":" in line:
                    key, rest = line.split(":", 1)
                    key = key.strip()
                    if key in fields:
                        # รูปแบบ "  12345 kB" → ดึงเฉพาะตัวเลข
                        num = "".join(ch for ch in rest if ch.isdigit())
                        fields[key] = int(num) if num else 0
    except Exception:
        pass
    return fields

def print_smaps(label: str, pid: int, size_mb: int) -> None:
    """
    พิมพ์ค่า smaps_rollup ย่อ เพื่อดู Shared_* และ Private_* ชัด ๆ
    """
    m = read_smaps_rollup_kb(pid)
    def f(k): return m.get(k, 0)
    print(
        f"[{label}][pid={pid}][size={size_mb} MB] smaps_rollup: "
        f"Rss={f('Rss')} kB, "
        f"Shared=({f('Shared_Clean')}/{f('Shared_Dirty')}) kB, "
        f"Private=({f('Private_Clean')}/{f('Private_Dirty')}) kB, "
        f"Pss={f('Pss')} kB"
    )


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


def run_trial(size_mb: int, smaps: bool = False) -> int:
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

    # 1) Parent: หลัง commit memory แต่ก่อน fork
    touch_memory(buf, page)
    print_status('parent', os.getpid(), size_mb, 'after-initialize-before-fork')
    if smaps:
        # โชว์ภาพรวม Shared/Private ของ parent ก่อน fork (ยังไม่มี child)
        print_smaps('parent', os.getpid(), size_mb)

    # Pipes for sync: parent->child (p2c), child->parent (c2p)
    p2c_r, p2c_w = os.pipe()
    c2p_r, c2p_w = os.pipe()

    pid = os.fork()
    if pid == 0:
        # ===== CHILD =====
        try:
            os.close(p2c_w)
            os.close(c2p_r)

            # 2) Child: ทันทีหลัง fork (ยังแชร์เพจกับ parent)
            print_status('child', os.getpid(), size_mb, 'just-after-fork')
            if smaps:
                # ตรงนี้คาดหวัง Shared_Clean สูง, Private_* ยังต่ำ
                print_smaps('child', os.getpid(), size_mb)

            # แจ้ง parent ว่า ready แล้ว
            os.write(c2p_w, b'R')
            # รอสัญญาณให้เริ่มเขียน
            os.read(p2c_r, 1)

            # 3) Child: เขียน 1 ไบต์/เพจ → กระตุ้น CoW
            modify_memory_xor(buf, page)

            # 4) Child: หลังแก้ไขเสร็จ → Private_* ควรเพิ่ม
            print_status('child', os.getpid(), size_mb, 'after-child-modify')
            if smaps:
                # ตรงนี้คาดหวัง Private_Dirty (หรือรวม Private_*) เพิ่มขึ้น
                print_smaps('child', os.getpid(), size_mb)

            # แจ้ง parent ว่าเสร็จแล้ว
            os.write(c2p_w, b'D')
        finally:
            try: os.close(p2c_r)
            except OSError: pass
            try: os.close(c2p_w)
            except OSError: pass
            os._exit(0)

    else:
        # ===== PARENT =====
        os.close(p2c_r)
        os.close(c2p_w)

        # 2) Parent: ทันทีหลัง fork (ยังแชร์เพจกับ child)
        print_status('parent', os.getpid(), size_mb, 'just-after-fork')
        if smaps:
            # ค่าจะคล้ายกับ child just-after-fork (แชร์เพจ)
            print_smaps('parent', os.getpid(), size_mb)

        # รอ child ready
        os.read(c2p_r, 1)
        # ส่งสัญญาณให้ child เริ่มเขียน
        os.write(p2c_w, b'G')
        # รอ child เสร็จ
        os.read(c2p_r, 1)

        # 4) Parent: หลัง child เขียนเสร็จ
        print_status('parent', os.getpid(), size_mb, 'after-child-modify')
        if smaps:
            # Parent ไม่ได้เขียนเอง → Private_* ของ parent ไม่ควรเด้งขึ้นเยอะ
            print_smaps('parent', os.getpid(), size_mb)

        # cleanup
        try: os.close(p2c_w)
        except OSError: pass
        try: os.close(c2p_r)
        except OSError: pass
        os.waitpid(pid, 0)
    return 0


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description='Copy-on-Write (CoW) demo (Linux only)')
    parser.add_argument('--sizes', type=str, default='50,75,100', help='Comma-separated MB sizes, default: 50,75,100')
    parser.add_argument('--smaps', action='store_true', help='พิมพ์ค่า /proc/<pid>/smaps_rollup ในแต่ละเฟสเพื่อโชว์ Shared/Private ชัดขึ้น')
    args = parser.parse_args(argv)

    try:
        sizes = parse_sizes_arg(args.sizes)
    except Exception as e:
        print(f"Invalid --sizes: {e}")
        return 2

    print(f"CoW demo starting (pid={os.getpid()}). Page size={os.sysconf('SC_PAGESIZE')} bytes.")
    print("NOTE: Run on Linux only. This program reads /proc to observe VmRSS.")

    for sz in sizes:
        if run_trial(sz, smaps=args.smaps) != 0:
            print(f"Trial with {sz} MB failed or skipped.")

    print("\nAll trials completed.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
