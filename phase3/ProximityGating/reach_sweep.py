#!/usr/bin/env python3
import subprocess, os

BIN = "./bin/augury"
AOP_ADDR = "0x200000000"
TRIALS = 5

def run_once(db_addr):
    for f in ("out/baseline.out", "out/aop.out"):
        if os.path.exists(f):
            os.remove(f)
    proc = subprocess.run([BIN, "256", "1", "32", "4", "1", db_addr, AOP_ADDR],
                           capture_output=True, text=True, timeout=15)
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

with open("reach_addrs2.txt") as f:
    pts = [l.strip().split(",") for l in f if l.strip()]

with open("reach_results2.csv", "w") as out:
    out.write("dist_mib,trial,test_speedup,train_speedup\n")
    for dist_mib, db_addr in pts:
        print(f"=== dist={dist_mib} MiB ===")
        for t in range(1, TRIALS+1):
            r = run_once(db_addr)
            if r is None:
                print(f"  trial {t}: FAIL")
                out.write(f"{dist_mib},{t},,\n")
                continue
            test_sp, train_sp = r
            print(f"  trial {t}: train={train_sp:.3f} test={test_sp:.3f}")
            out.write(f"{dist_mib},{t},{test_sp:.4f},{train_sp:.4f}\n")
        out.flush()
