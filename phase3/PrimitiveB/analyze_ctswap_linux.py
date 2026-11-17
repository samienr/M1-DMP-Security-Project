#!/usr/bin/env python3
"""
Analyze Primitive B (GoFetch ct-swap) results from this project's Asahi
Linux port of the attack (see phase3/ASAHI_REPORT.md for the full port
writeup).

Unlike the macOS original, each run here is driven against a single victim
process with a *known, fixed* secret for its whole lifetime (we launch
`ctswap_victim 0` or `ctswap_victim 1` ourselves), and each run
independently re-does the full eviction-set-generation + gadget search
(no gadget is cached/reused between runs). So this script's job isn't
"recover an unknown secret" -- it's the controlled-experiment version:
given attacker stdout logs from a known-secret-1 run and a known-secret-0
run, tally how often the attacker's own per-round verdict
("Secret Key is 0!" / "Secret Key is 1!" / "Noisy Measuremnts!") matches
ground truth, and report whether the secret=0 vs secret=1 "signal detected"
rates are statistically distinguishable.

Usage:
    ./analyze_ctswap_linux.py results/attacker_sk1.log results/attacker_sk0.log
"""
import argparse
import math
import re
import sys


def tally(log_path: str) -> dict[str, int]:
    text = open(log_path).read()
    counts = {"0": 0, "1": 0, "noisy": 0}
    for m in re.finditer(r"Secret Key is ([01])!|Noisy Measuremnts!", text):
        if m.group(1) == "0":
            counts["0"] += 1
        elif m.group(1) == "1":
            counts["1"] += 1
        else:
            counts["noisy"] += 1
    return counts


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / denom
    return (max(0.0, (center - margin) * 100), min(100.0, (center + margin) * 100))


def two_proportion_z(s1: int, n1: int, s2: int, n2: int) -> tuple[float, float]:
    p1, p2 = s1 / n1, s2 / n2
    p_pool = (s1 + s2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return (float("inf") if p1 != p2 else 0.0, 0.0 if p1 != p2 else 1.0)
    z = (p1 - p2) / se
    # two-sided normal p-value
    p_value = math.erfc(abs(z) / math.sqrt(2))
    return z, p_value


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sk1_log", help="attacker stdout log from a known secret=1 victim run")
    ap.add_argument("sk0_log", help="attacker stdout log from a known secret=0 victim run")
    args = ap.parse_args()

    c1 = tally(args.sk1_log)
    c0 = tally(args.sk0_log)
    n1 = sum(c1.values())
    n0 = sum(c0.values())

    if n1 == 0 or n0 == 0:
        print("One of the logs has zero parsed measurement rounds -- "
              "did the run reach 'Start Leaking'? (search may not have converged)",
              file=sys.stderr)
        sys.exit(1)

    print("=" * 70)
    print("Primitive B (GoFetch ct-swap) -- Asahi Linux port results")
    print("=" * 70)
    print(f"secret=1 victim: n={n1}  ->  '1' (correct): {c1['1']}  "
          f"'0' (wrong): {c1['0']}  noisy: {c1['noisy']}")
    print(f"secret=0 victim: n={n0}  ->  '1' (wrong):   {c0['1']}  "
          f"'0' (correct): {c0['0']}  noisy: {c0['noisy']}")
    print()

    p1_signal = c1["1"] / n1 * 100
    p0_signal = c0["1"] / n0 * 100
    lo1, hi1 = wilson_ci(c1["1"], n1)
    lo0, hi0 = wilson_ci(c0["1"], n0)
    print(f"P(attacker reports '1' | secret=1) = {p1_signal:.1f}%  95% CI [{lo1:.1f}%, {hi1:.1f}%]")
    print(f"P(attacker reports '1' | secret=0) = {p0_signal:.1f}%  95% CI [{lo0:.1f}%, {hi0:.1f}%]")
    print()

    z, p = two_proportion_z(c1["1"], n1, c0["1"], n0)
    print(f"Two-proportion z-test for a real secret-dependent difference:")
    print(f"  z = {z:.3f}, two-sided p = {p:.5f}")
    if p < 0.05:
        print("  -> statistically significant at p<0.05: the 'signal detected' rate")
        print("     genuinely differs between the two secrets on this run pair.")
    else:
        print("  -> not statistically significant at this sample size.")
    print()
    print("Caveats: each run independently re-ran the full eviction-set-generation")
    print("+ gadget search (no gadget persistence across runs), so the two runs")
    print("used *different* discovered (eviction-set, target-address) gadgets, not")
    print("a single fixed channel tested against both secrets. pp_threshold (680)")
    print("was carried over unchanged from the macOS README example and was not")
    print("independently calibrated for this hardware/timer. Treat this as an")
    print("existence result (a real, if weak, secret-dependent channel exists)")
    print("rather than a calibrated accuracy figure comparable to GoFetch's own")
    print("macOS numbers.")


if __name__ == "__main__":
    main()
