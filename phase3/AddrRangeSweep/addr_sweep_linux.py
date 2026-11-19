#!/usr/bin/env python3
"""Linux replacement for addrs.sh's orchestration, since this machine has
neither zsh/conda nor numpy/pandas installed. Same retry-until-valid logic
as the original script (and the same train_speedup>=2.0 success gate that
get_avg.py uses), implemented with the stdlib only.

Usage: ./addr_sweep_linux.py addrs.dat out.csv
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
MAX_RETRIES = 2


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
        return None, "timeout"
    if proc.returncode != 0:
        return None, f"crashed (rc={proc.returncode}): {proc.stdout[-300:]}{proc.stderr[-300:]}"
    if not (os.path.exists("out/baseline.out") and os.path.exists("out/aop.out")):
        return None, "no output files"
    return parse_outputs(), None


def parse_outputs():
    def read_means(fname):
        with open(fname) as f:
            lines = f.readlines()[2:]  # skip addr line + header
        tests, trains = [], []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            t, tr = line.split(",")
            tests.append(int(t))
            trains.append(int(tr))
        n = len(tests)
        return sum(tests) / n, sum(trains) / n, n

    base_test, base_train, n_base = read_means("out/baseline.out")
    aop_test, aop_train, n_aop = read_means("out/aop.out")
    return {
        "base_test": base_test, "base_train": base_train, "n_base": n_base,
        "aop_test": aop_test, "aop_train": aop_train, "n_aop": n_aop,
    }


def main():
    addrs_file, out_csv = sys.argv[1], sys.argv[2]
    with open(addrs_file) as f:
        addrs = [l.strip() for l in f if l.strip()]

    write_header = not os.path.exists(out_csv)
    with open(out_csv, "a") as out:
        if write_header:
            out.write("addr,retries,status,base_test,aop_test,test_speedup,"
                       "base_train,aop_train,train_speedup,success\n")

        for addr in addrs:
            print(f"==== {addr} ====")
            last_result = None
            last_err = None
            success = False
            retries_used = 0
            for attempt in range(1, MAX_RETRIES + 1):
                retries_used = attempt
                result, err = run_once(addr)
                if result is None:
                    last_err = err
                    print(f"  attempt {attempt}: {err}")
                    if "crashed" in (err or "") and "MAP_FAILED" in (err or ""):
                        break  # deterministic failure, no point retrying
                    continue
                last_result = result
                train_speedup = result["base_train"] / result["aop_train"]
                test_speedup = result["base_test"] / result["aop_test"] if result["aop_test"] else float("inf")
                print(f"  attempt {attempt}: train_speedup={train_speedup:.3f} "
                      f"test_speedup={test_speedup:.3f}")
                if train_speedup >= 2.0:
                    success = True
                    break

            if last_result is None:
                out.write(f"{addr},{retries_used},FAIL:{last_err},,,,,,,{False}\n")
                out.flush()
                continue

            train_speedup = last_result["base_train"] / last_result["aop_train"]
            test_speedup = (last_result["base_test"] / last_result["aop_test"]
                             if last_result["aop_test"] else float("inf"))
            out.write(f"{addr},{retries_used},OK,{last_result['base_test']:.2f},"
                      f"{last_result['aop_test']:.2f},{test_speedup:.4f},"
                      f"{last_result['base_train']:.2f},{last_result['aop_train']:.2f},"
                      f"{train_speedup:.4f},{success}\n")
            out.flush()


if __name__ == "__main__":
    main()
