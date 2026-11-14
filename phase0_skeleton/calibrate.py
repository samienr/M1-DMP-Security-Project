#!/usr/bin/env python3
"""
Phase 0 calibration driver (step 5 of the action item).

Does NOT modify main.c, evset.c, or the Makefile. It:
  1. Builds phase0_skeleton the normal way (`make`), unmodified.
  2. Builds calibrate_miss.c against your existing timing.c/core_pin.c
     with a couple of direct clang calls (no Makefile edits).
  3. Runs each binary N times, parses the latency each one prints,
     and reports warm vs. miss statistics plus a suggested threshold.

calibrate_miss.c (v2) issues a hardware barrier between the flush and
the timed access, and reports the median of many internal trials per
run rather than a single sample -- see the comment at the top of that
file for why. Its stderr output also warns per-run if a chunk of those
internal trials look like failed evictions rather than ordinary noise.

Usage:
    ./calibrate.py                  # 25 runs of each binary
    ./calibrate.py --runs 30
    ./calibrate.py --csv m1_calibration.csv
    ./calibrate.py --skip-build      # binaries already built, just run them
    ./calibrate.py --miss-trials 101 # more internal trials per calibrate_miss run

Run this once on the M1 and once on the M4 Pro -- expect different
thresholds on each, per the project's Phase 0 notes.
"""
import argparse
import csv
import re
import statistics
import subprocess
import sys
from pathlib import Path

WARM_RE = re.compile(r"warm \(hit\) access latency:\s*(\d+)\s*ns")
MISS_RE = re.compile(r"miss \(evicted\) access latency:\s*(\d+)\s*ns")


def build(skip_build):
    if skip_build:
        return
    print("[calibrate] building phase0_skeleton via `make`...")
    subprocess.run(["make"], check=True)

    print("[calibrate] building calibrate_miss (reuses timing.c/core_pin.c, "
          "no Makefile changes)...")
    subprocess.run(["clang", "-O0", "-Wall", "-Wextra",
                     "-c", "timing.c", "core_pin.c"], check=True)
    subprocess.run(["clang", "-O0", "-Wall", "-Wextra",
                     "-o", "calibrate_miss",
                     "calibrate_miss.c", "timing.o", "core_pin.o"], check=True)
    print()


def run_once(binary_path, pattern, extra_args=None):
    cmd = [binary_path] + (extra_args or [])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        print(f"[calibrate] '{binary_path}' not found.", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"[calibrate] {binary_path} timed out, skipping this run", file=sys.stderr)
        return None

    if proc.returncode != 0:
        print(f"[calibrate] {binary_path} failed (exit {proc.returncode}):\n{proc.stderr}",
              file=sys.stderr)
        return None

    m = pattern.search(proc.stdout)
    if not m:
        print(f"[calibrate] expected pattern not found in {binary_path} output:\n{proc.stdout}",
              file=sys.stderr)
        return None
    return int(m.group(1))


def summarize(label, values):
    values_sorted = sorted(values)
    stats = {
        "n": len(values),
        "min": values_sorted[0],
        "max": values_sorted[-1],
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }
    print(f"{label:>16}: n={stats['n']:<3} min={stats['min']:>6}  max={stats['max']:>6}  "
          f"mean={stats['mean']:>8.1f}  median={stats['median']:>8.1f}  stdev={stats['stdev']:>7.1f}")
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=25,
                     help="number of times to run each binary (default 25)")
    ap.add_argument("--csv", default="calibration_results.csv",
                     help="where to write per-run raw data (default calibration_results.csv)")
    ap.add_argument("--skip-build", action="store_true",
                     help="assume phase0_skeleton and calibrate_miss are already built")
    ap.add_argument("--miss-trials", type=int, default=None,
                     help="internal trials per calibrate_miss run (its own default is 51)")
    args = ap.parse_args()

    if not Path("main.c").exists():
        print("[calibrate] run this from the directory containing main.c/timing.c/"
              "core_pin.c/evset.c/calibrate_miss.c", file=sys.stderr)
        sys.exit(1)

    build(args.skip_build)

    warm_vals, miss_vals, rows = [], [], []

    print(f"[calibrate] running ./phase0_skeleton and ./calibrate_miss {args.runs} times each...\n")
    miss_extra_args = [str(args.miss_trials)] if args.miss_trials else None
    for i in range(args.runs):
        warm_ns = run_once("./phase0_skeleton", WARM_RE)
        miss_ns = run_once("./calibrate_miss", MISS_RE, miss_extra_args)
        if warm_ns is None or miss_ns is None:
            continue
        warm_vals.append(warm_ns)
        miss_vals.append(miss_ns)
        rows.append((i, warm_ns, miss_ns))
        print(f"  run {i + 1:2d}/{args.runs}:  warm = {warm_ns:>6} ns   miss = {miss_ns:>6} ns")

    if len(warm_vals) < 2 or len(miss_vals) < 2:
        print("\n[calibrate] not enough usable runs to compute statistics.", file=sys.stderr)
        sys.exit(1)

    with open(args.csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["run", "warm_ns", "miss_ns"])
        w.writerows(rows)
    print(f"\n[calibrate] raw per-run data written to {args.csv}")

    print("\n--- summary ---")
    warm_stats = summarize("warm (hit)", warm_vals)
    miss_stats = summarize("miss (evicted)", miss_vals)

    gap = miss_stats["min"] - warm_stats["max"]
    print(f"\ngap between warm max and miss min: {gap} ns")

    if gap <= 0:
        print(
            "WARNING: your hit and miss distributions overlap (gap <= 0).\n"
            "A single threshold will misclassify some accesses. Consider:\n"
            "  - increasing FLUSH_BYTES in calibrate_miss.c\n"
            "  - re-checking `sudo powermetrics --samplers tasks` for E-core drift\n"
            "  - running more iterations to rule out a one-off outlier\n"
        )
        suggested = (warm_stats["median"] + miss_stats["median"]) / 2
    else:
        midpoint = (warm_stats["median"] + miss_stats["median"]) / 2
        suggested = min(max(midpoint, warm_stats["max"] + 1), miss_stats["min"] - 1)

    print(f"suggested threshold_ns: {suggested:.0f}")
    print(
        "\nUse this value as threshold_ns wherever you call evset_evicts() in "
        "your own later code -- main.c's current warm_ns*3 placeholder is still "
        "unmodified and is only a first-run smoke test, per the README."
    )


if __name__ == "__main__":
    main()
