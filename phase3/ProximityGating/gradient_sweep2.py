#!/usr/bin/env python3
"""Same as gradient_sweep.py but also captures aop's own (ASLR'd) address
per trial, to test whether hit/miss is explained by distance(aop,
data_buffer) rather than data_buffer's absolute address.
"""
import re
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

AOP_RE = re.compile(r"Aligned to 2MB boundary at (0x[0-9a-f]+)")


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
    m = AOP_RE.search(proc.stdout)
    aop_addr = m.group(1) if m else None
    if not (os.path.exists("out/baseline.out") and os.path.exists("out/aop.out")):
        return None
    result = parse_outputs()
    return (aop_addr,) + result


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
        out.write("addr,aop_addr,trial,base_test,aop_test,test_speedup,base_train,aop_train,train_speedup\n")
        for addr in addrs:
            print(f"==== {addr} ====")
            for trial in range(1, TRIALS_PER_ADDR + 1):
                result = run_once(addr)
                if result is None:
                    print(f"  trial {trial}: FAIL")
                    out.write(f"{addr},,{trial},,,,,,\n")
                    continue
                aop_addr, base_test, base_train, aop_test, aop_train = result
                test_sp = base_test / aop_test if aop_test else float("inf")
                train_sp = base_train / aop_train if aop_train else float("inf")
                dist = (int(aop_addr, 16) - int(addr, 16)) if aop_addr else None
                print(f"  trial {trial}: aop={aop_addr} dist={dist} train_speedup={train_sp:.3f}")
                out.write(f"{addr},{aop_addr},{trial},{base_test:.2f},{aop_test:.2f},{test_sp:.4f},"
                          f"{base_train:.2f},{aop_train:.2f},{train_sp:.4f}\n")
            out.flush()


if __name__ == "__main__":
    main()
