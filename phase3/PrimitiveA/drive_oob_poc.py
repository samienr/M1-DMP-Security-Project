#!/usr/bin/env python3
"""
Driver for Augury Primitive A (out-of-bounds read PoC, Algorithm 3).

Scope note: this driver only exercises the `mach_absolute_time`-timed
binary (built with MACH=1 KEXT=0). We deliberately do not build/load
the Augury repo's custom PMC kernel extension: on this machine that
would require disabling SIP and signing a kext in Xcode, which is a
system security change we're keeping out of the automated pipeline.
The hit/miss gap we measure (see the histogram this script prints) is
tens-to-hundreds of timer units, far above mach_absolute_time's ~1ns
tick, so the timer's resolution is not the limiting factor here -- the
gap to the paper's 92.0% (PMC) number is attributable to
scheduler/syscall noise around mach_absolute_time(), not quantization.
See the Phase 3 writeup for the full justification.

Runs the oob-poc binary `trials` times, each time feeding it a random
candidate choice (0/1/2) via stdin, parsing its per-candidate timing
output, and scoring whether the FIRST measurement per candidate
correctly identifies the chosen (prefetched) pointer.

Why only the first measurement per candidate:
The binary flushes the cache once, before training, then probes each
of the 3 candidates. For whichever candidate is probed first, that
probe is a clean test of "was this in cache after training." But the
binary re-probes each candidate two more times AFTER that first round
-- and by then, every candidate has already been touched once by its
own first probe, so a fast second/third reading just means "I read
this a moment ago," not "the DMP prefetched this." Including those in
an average would dilute (and can even flip) the real signal. Only
times[k][0] is a valid, uncontaminated classification signal.
"""
import argparse
import csv
import math
import random
import re
import subprocess
import sys

# Augury's own reported accuracy for this PoC (Algorithm 3), for the
# two timer sources they used. We only reproduce the second one here.
AUGURY_PMC_ACCURACY = 92.0
AUGURY_MACH_ACCURACY = 70.2


def parse_times(output: str) -> dict[int, list[int]]:
    times: dict[int, list[int]] = {0: [], 1: [], 2: []}
    current = None
    in_block = False
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if "Times were" in line:
            in_block = True
            continue
        if not in_block:
            continue
        m = re.match(r"^(\d+):$", line)
        if m:
            current = int(m.group(1))
            continue
        if line.isdigit() and current is not None:
            times[current].append(int(line))
    return times


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion, as percentages."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / denom
    return (max(0.0, (center - margin) * 100), min(100.0, (center + margin) * 100))


def ascii_histogram(values: list[int], label: str, width: int = 40) -> str:
    if not values:
        return f"  {label}: (no data)"
    buckets = [0, 1, 2, 4, 8, 16, 32, 64, 128, 256, float("inf")]
    counts = [0] * (len(buckets) - 1)
    for v in values:
        for i in range(len(buckets) - 1):
            if buckets[i] <= v < buckets[i + 1]:
                counts[i] += 1
                break
    maxc = max(counts) or 1
    lines = [f"  {label} (n={len(values)}):"]
    for i, c in enumerate(counts):
        lo, hi = buckets[i], buckets[i + 1]
        hi_s = "+" if math.isinf(hi) else f"-{int(hi) - 1}"
        bar = "#" * int(c / maxc * width)
        lines.append(f"    [{int(lo):>4}{hi_s:<5}] {bar} {c}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("binary", help="path to the oob-poc mach_absolute_time binary")
    ap.add_argument("trials", type=int, help="number of trials to run")
    ap.add_argument("out_csv", help="path to write the per-trial CSV")
    ap.add_argument("--seed", type=int, default=None, help="RNG seed for reproducibility")
    ap.add_argument("--timeout", type=float, default=60.0, help="per-trial subprocess timeout (s)")
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    rows = []
    correct = 0
    hit_times: list[int] = []   # first_times[chosen]      -- should be fast
    miss_times: list[int] = []  # first_times[not chosen]  -- should be slow

    for trial in range(args.trials):
        chosen = random.choice([0, 1, 2])
        try:
            proc = subprocess.run(
                [args.binary], input=f"{chosen}\n",
                capture_output=True, text=True, timeout=args.timeout,
            )
        except subprocess.TimeoutExpired:
            print(f"trial {trial}: TIMED OUT, skipping", file=sys.stderr)
            continue

        times = parse_times(proc.stdout)
        if not all(times[k] for k in (0, 1, 2)):
            print(f"trial {trial}: failed to parse output, skipping", file=sys.stderr)
            continue

        first_times = {k: v[0] for k, v in times.items()}
        predicted = min(first_times, key=first_times.get)
        is_correct = int(predicted == chosen)
        correct += is_correct

        hit_times.append(first_times[chosen])
        miss_times.extend(first_times[k] for k in (0, 1, 2) if k != chosen)

        rows.append({
            "trial": trial,
            "chosen": chosen,
            "predicted": predicted,
            "correct": is_correct,
            "t0_first": first_times[0],
            "t1_first": first_times[1],
            "t2_first": first_times[2],
            # Raw data kept for reference/debugging -- NOT used for scoring.
            "t0_all": times[0],
            "t1_all": times[1],
            "t2_all": times[2],
        })

    n = len(rows)
    if n == 0:
        print("No successful trials; nothing to report.", file=sys.stderr)
        sys.exit(1)

    accuracy = correct / n * 100
    lo, hi = wilson_ci(correct, n)

    with open(args.out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    print("=" * 70)
    print("Primitive A (Augury Algorithm 3) -- mach_absolute_time results")
    print("=" * 70)
    print(f"Trials:              {n} (of {args.trials} requested)")
    print(f"Accuracy:            {accuracy:.1f}% ({correct}/{n})")
    print(f"95% CI (Wilson):     [{lo:.1f}%, {hi:.1f}%]")
    print()
    print(f"Augury paper, PMC timer:              {AUGURY_PMC_ACCURACY:.1f}%  (not reproduced -- see header note)")
    print(f"Augury paper, mach_absolute_time:      {AUGURY_MACH_ACCURACY:.1f}%")
    print(f"This replication, mach_absolute_time:  {accuracy:.1f}%  (delta: {accuracy - AUGURY_MACH_ACCURACY:+.1f} pts)")
    print()
    print("Hit/miss timing separation (first-probe reading, in timer units):")
    print(ascii_histogram(hit_times, "chosen candidate (expected: fast/hit)"))
    print(ascii_histogram(miss_times, "other candidates (expected: slow/miss)"))
    print()
    print(f"Wrote per-trial data to {args.out_csv}")


if __name__ == "__main__":
    main()
