#!/usr/bin/env python3
"""Measure DMP activation *magnitude* (not just on/off) as a function of
distance from the activation boundary found in the earlier address-range
sweep. Runs N independent trials per address (not retry-until-success)
to get a mean/std per point, since a single run is noisy even deep in
the confirmed-on region.
"""
import subprocess
import sys
import os

BIN = "./bin/augury"
TRAIN_LEN = 256
OFFS = 1
REPS = 32
CORE = 4
STRIDE = 1
TRIALS_PER_ADDR = 10


def run_once(addr):
    for f in ("out/baseline.out", "out/aop.out"):
        if os.path.exists(f):
            os.remove(f)
    try:
        proc = subprocess.run(
            [BIN, str(TRAIN_LEN), str(OFFS), str(REPS), str(CORE), str(STRIDE), addr],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0:
        return None
    if not (os.path.exists("out/baseline.out") and os.path.exists("out/aop.out")):
        return None
    return parse_outputs()


def parse_outputs():
    def read_means(fname):
        with open(fname) as f:
            lines = f.readlines()[2:]
        tests, trains = [], []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            t, tr = line.split(",")
            tests.append(int(t))
            trains.append(int(tr))
        n = len(tests)
        return sum(tests) / n, sum(trains) / n

    base_test, base_train = read_means("out/baseline.out")
    aop_test, aop_train = read_means("out/aop.out")
    return base_test, base_train, aop_test, aop_train


def main():
    addrs_file, out_csv = sys.argv[1], sys.argv[2]
    with open(addrs_file) as f:
        addrs = [l.strip() for l in f if l.strip()]

    with open(out_csv, "w") as out:
        out.write("addr,trial,base_test,aop_test,test_speedup,base_train,aop_train,train_speedup\n")
        for addr in addrs:
            print(f"==== {addr} ====")
            for trial in range(1, TRIALS_PER_ADDR + 1):
                result = run_once(addr)
                if result is None:
                    print(f"  trial {trial}: FAIL")
                    out.write(f"{addr},{trial},,,,,,\n")
                    continue
                base_test, base_train, aop_test, aop_train = result
                test_sp = base_test / aop_test if aop_test else float("inf")
                train_sp = base_train / aop_train if aop_train else float("inf")
                print(f"  trial {trial}: train_speedup={train_sp:.3f} test_speedup={test_sp:.3f}")
                out.write(f"{addr},{trial},{base_test:.2f},{aop_test:.2f},{test_sp:.4f},"
                          f"{base_train:.2f},{aop_train:.2f},{train_sp:.4f}\n")
            out.flush()


if __name__ == "__main__":
    main()
