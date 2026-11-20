#!/usr/bin/env python3
"""Test whether the ~3-4 GiB AoP-to-target proximity reach found in
phase3/ProximityGating/ is (a) symmetric -- same falloff whether
data_buffer is placed above or below aop -- and (b) holds at other
absolute locations, not just the one spot-checked (0x200000000).
"""
import subprocess
import os

BIN = "./bin/augury"
TRAIN_LEN, OFFS, REPS, CORE, STRIDE = "256", "1", "32", "4", "1"
DATA_BUFFER_SIZE = 128 * 8388617  # CACHE_LINE_SIZE * PRNG_m, see augury.c
TRIALS = 3

GAPS_MIB = [8, 1024, 2048, 2816, 3072, 3328, 3584, 3840, 4096, 6144]
AOP_LOCATIONS = [0x600000000, 0xA00000000]  # two fresh low "dead zone" addrs


def run_once(data_buffer_addr, aop_addr):
    for f in ("out/baseline.out", "out/aop.out"):
        if os.path.exists(f):
            os.remove(f)
    proc = subprocess.run(
        [BIN, TRAIN_LEN, OFFS, REPS, CORE, STRIDE, hex(data_buffer_addr), hex(aop_addr)],
        capture_output=True, text=True, timeout=15,
    )
    if proc.returncode != 0:
        return None
    def rm(fname):
        with open(fname) as f:
            lines = f.readlines()[2:]
        tests, trains = [], []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            t, tr = line.split(",")
            tests.append(int(t)); trains.append(int(tr))
        return sum(tests)/len(tests), sum(trains)/len(trains)
    bt, btr = rm("out/baseline.out")
    at, atr = rm("out/aop.out")
    return bt/at, btr/atr


def main():
    with open("symmetry_results.csv", "w") as out:
        out.write("aop_loc,direction,gap_mib,trial,test_speedup,train_speedup\n")
        for aop in AOP_LOCATIONS:
            for direction in ("above", "below"):
                for gap_mib in GAPS_MIB:
                    gap = gap_mib * 1024 * 1024
                    PAGE = 0x4000
                    if direction == "above":
                        data_buffer_addr = aop + gap
                    else:
                        data_buffer_addr = (aop - gap - DATA_BUFFER_SIZE) & ~(PAGE - 1)
                    print(f"=== aop={hex(aop)} dir={direction} gap={gap_mib}MiB db={hex(data_buffer_addr)} ===")
                    for t in range(1, TRIALS + 1):
                        r = run_once(data_buffer_addr, aop)
                        if r is None:
                            print(f"  trial {t}: FAIL")
                            out.write(f"{hex(aop)},{direction},{gap_mib},{t},,\n")
                            continue
                        test_sp, train_sp = r
                        print(f"  trial {t}: train={train_sp:.3f} test={test_sp:.3f}")
                        out.write(f"{hex(aop)},{direction},{gap_mib},{t},{test_sp:.4f},{train_sp:.4f}\n")
                    out.flush()


if __name__ == "__main__":
    main()
