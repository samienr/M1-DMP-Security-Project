# Phase 3 on Asahi Linux (M1) — Exploit Primitives

This supplements the macOS Phase 3 work with a from-scratch port and run of
both exploit primitives on this machine's native Asahi Linux (Fedora remix,
kernel `7.2.12-402.asahi.fc45.aarch64+16k`, 8-core M1: 4 Icestorm + 4
Firestorm, 16 KiB native pages).

Per the project plan, Primitive B (ct-swap) and the Asahi angle are both
explicitly scoped to be cuttable/deferred (Phase 3 is nominally macOS-only,
Asahi is Phase 4). This report documents an out-of-plan attempt to run both
primitives on Asahi directly, at the user's request -- treat the Primitive B
section as exploratory/novel-investigation material, not a substitute for
the planned macOS Primitive B replication.

## Primitive A (Augury Algorithm 3, OOB read) — done

`augury/oob-poc.c`'s Linux timer path (already present in the repo at
commit `a6a1b89`, no new porting needed) was built natively with:

```
cd augury
make CC=gcc MACH=1 KEXT=0 bin/oob-poc
```

Binary copied to `phase3/PrimitiveA/oob-poc-mach-linux`. Driven with the
existing `drive_oob_poc.py`, two independent 500-trial runs (different RNG
seeds), from inside this same Claude Code session (not a clean bare
terminal -- see caveat below):

| Run | Trials | Accuracy | 95% CI (Wilson) |
|---|---|---|---|
| 1 (seed 1) | 496/500 | 77.4% (384/496) | [73.5%, 80.9%] |
| 2 (seed 2) | 490/500 | 75.1% (368/490) | [71.1%, 78.7%] |
| **Pooled** | 986 | **76.3% (752/986)** | — |

Comparison points:
- Augury paper, PMC timer: 92.0% (not reproduced; out of scope, see
  `phase3/PrimitiveA/drive_oob_poc.py` docstring)
- Augury paper, `mach_absolute_time`: 70.2%
- This machine, Linux `clock_gettime(CLOCK_MONOTONIC)`: **76.3%**, i.e.
  **above** the paper's own mach-timer figure.
- Mac (this project, clean bare-terminal run, `mach_absolute_time`): 48.3%,
  95% CI [45.2%, 51.4%] -- see `phase3/PrimitiveA/run_log.txt`.

**Noteworthy finding:** Linux/Asahi reproduced a *higher* OOB-read accuracy
than both this project's own macOS run and the paper's macOS number, despite
running from inside the same kind of contended environment (this Claude Code
session) that tanked the Mac's in-session number to 39% (see handoff notes).
A plausible explanation, not yet confirmed: `pin_cpu()`'s Linux
implementation uses `sched_setaffinity()`, a hard pin enforced by the kernel
scheduler, whereas macOS's `pin_cpu()` only sets a QoS class -- a scheduling
*hint*, not a binding affinity guarantee. If so, the DMP-timing signal would
be systematically less disturbed by competing processes (e.g. this very
session) on Linux than on macOS for exactly this reason. This is a genuine
OS-scheduler-interaction result in the spirit of the Phase 4 "Asahi
characterization" angle, surfaced incidentally while doing Phase 3 on this
machine -- worth a deliberate follow-up measurement (e.g. comparing
`sched_setaffinity` vs an unpinned control on Linux) before claiming it in
the final report.

Caveat carried over from the Mac work: all of the above Linux numbers were
measured from inside this Claude Code session, not a clean bare terminal,
so some contention noise is still possible. Given Linux's apparent
resistance to this effect, a clean-terminal confirmation run was not judged
essential, but is cheap to re-run (`python3 drive_oob_poc.py
./oob-poc-mach-linux 500 <out.csv>`) if the final report wants it.

Artifacts: `phase3/PrimitiveA/oob-poc-mach-linux` (binary),
`out_mach_linux_1.csv`, `out_mach_linux_2.csv`, `run_log_linux.txt`.

## Primitive B (GoFetch ct-swap, Section 5) — ported and running; gadget search in progress

### Why this needed a real port, not just a recompile

GoFetch's own README scopes the ct-swap/RSA/DH/Kyber/Dilithium PoCs to
macOS specifically. Concretely, two things don't exist on Linux at all:

1. **`dyld_search`** (`crypto_attacker/examples/dyld_search.rs`) shells out
   to macOS's `vmmap` and scans for `.dylib`/dyld-cache mappings. It works
   *only* by inspecting the calling (attacker) process's own memory map,
   relying on the fact that macOS's dyld shared cache is mapped at the same
   virtual address in literally every process on the machine until the next
   reboot -- so "valid in my own map" implies "valid in the victim's map
   too," with zero cross-process introspection. Linux has no equivalent
   single, unconditionally-shared cache.
2. **`libaugury-ffi-sys`'s C timer/pin shim** (`c_augury.c`) used
   `clock_gettime_nsec_np` and `pthread_set_qos_class_self_np`/
   `QOS_CLASS_*`, all Darwin-only.

### What was ported

- `libaugury-ffi-sys/src/c_augury.c` -- added a Linux branch for
  `get_time_nano` (`clock_gettime(CLOCK_MONOTONIC)`, same approach as
  Primitive A) and `pin_cpu` (`sched_setaffinity` + `setpriority`), under
  `#ifdef __APPLE__ / #else`. Also fixed a latent, platform-independent bug
  (`volatile uint64_t**` initialized from a non-volatile cast -- only a
  warning on older GCC, a hard error on this machine's GCC 14+ default C
  conformance mode) in `flush_evset`.
- `libaugury-ffi-sys/build.rs` -- removed a hardcoded
  `.target("aarch64-apple-darwin")` that forced every build, macOS or not,
  through the Darwin target triple.
- `evict-rs/src/lib.rs` -- its own separate `pin_cpu` called
  `libc::pthread_set_qos_class_self_np`/`qos_class_t`, symbols that don't
  exist in the `libc` crate's Linux bindings at all (a hard *compile*
  error on Linux, not a runtime one). Added a `sched_setaffinity`-based
  Linux branch, gated the macOS one behind `#[cfg(target_os = "macos")]`.
- `evict-rs/src/allocator.rs` -- found genuine dead code: a
  `#[cfg(target_os = "linux")] l2_evset_gen` that calls `parse_pfn`, a
  function with no definition anywhere in the crate. Gated exactly onto
  our target, it would have broken the Linux build outright; it isn't used
  by the ct-swap path either way (that uses the OS-agnostic, purely
  timing-based `eviction_set_gen64`). Commented out with an explanation
  rather than deleted, in case someone picks the pagemap-based approach
  back up later (note: that would also need root -- `/proc/pid/pagemap`
  PFNs are zeroed for unprivileged readers on modern kernels).
- New `crypto_attacker/examples/linux_dyld_search.rs` -- Linux replacement
  for `dyld_search`. Approach: launch both attacker and victim under
  `setarch $(uname -m) -R` (`personality(ADDR_NO_RANDOMIZE)`, no root
  needed). With ASLR off, shared-library placement becomes deterministic,
  and -- confirmed empirically on this exact machine, see below -- that
  placement is *identical* across different binaries as long as they have
  the same dynamic dependency list (checked via `ldd`: both attacker and
  victim pull in just `ld-linux-aarch64.so.1`, `libc.so.6`,
  `libgcc_s.so.1`). The tool reads its own `/proc/self/maps`, merges
  contiguous same-file VMAs, and keeps the largest span (here, all of
  `libc.so.6`: 113 pages / ~1.77 MiB -- comparable to the >=200-page
  threshold the macOS original required for its dyld-cache span).

  **Fidelity note for the final report:** this is a deliberately weaker
  assumption than the macOS original. dyld-cache sharing holds between
  *any* two macOS processes, no coordination needed; our ASLR-off trick
  only holds between processes we've verified have matching dynamic
  dependency lists. That's true here because we control both binaries, but
  a real blind attacker normally wouldn't get this for free. Call this out
  explicitly as a known reduced-fidelity substitution.

  **Empirical validation:** rather than trust the determinism claim
  theoretically, it was checked directly against a real orphaned victim
  process's `/proc/<pid>/maps`: victim's `libc.so.6` span was
  `0xfffff7d80000`-`0xfffff7f44000`, byte-for-byte identical to
  `linux_dyld_search`'s own output run separately. (An earlier attempt at
  this check was confounded by a bash scripting bug -- `cmd1 && cmd2 &`
  backgrounds the *wrapping subshell*, not the final exec'd process, so
  `$!` pointed at a bash wrapper, not the victim, and `grep libc.so.6` was
  silently matching the wrapper's own unrelated, ASLR'd libc mapping. Fixed
  by checking the real child PID via `ps`/`/proc/<pid>/cmdline` instead of
  trusting `$!` through a compound command.)

### What did *not* need porting

The actual Prime+Probe timer the ct-swap attack uses
(`evict_rs::MyTimer`/`CounterTimer`, `evict-rs/src/multithread_counter.rs`)
is architecture-generic AArch64 assembly (a dedicated busy-spin counter
thread + `dsb ish`/`isb sy` barriers), not `kperf`/PMC. It needed no
changes at all, and -- importantly -- this means **Primitive B does not
need GoFetch's `linuxsetup` kernel module or `pmuctl`, and needs no root**,
unlike what was initially assumed. That infrastructure is only for
GoFetch's separate `re/` PMC-based reverse-engineering suite.

### Current run status

With both the victim (`ctswap_victim 1`, i.e. secret=1) and the attacker
(`ctswap_attacker 16 680 8`) launched under `setarch $(uname -m) -R`:

- **L2 eviction-set generation (`eviction_set_gen64`): works cleanly.**
  Clear cached-vs-evicted separation on the `CounterTimer`: ~108 ticks
  cached vs. ~269 ticks evicted, 100% eviction rate on every one of the 64
  generated eviction sets. This is a *cleaner* signal-to-noise ratio than
  Primitive A's `clock_gettime`-based timing showed, consistent with this
  being GoFetch's own chosen mechanism for exactly this reason (it's
  unmodified original code, used identically on macOS -- not a fidelity
  downgrade introduced by this port).
- **Calibration (contention detection): works.** First page offset tried
  split the 64 evsets into 23 conflicting / 41 non-conflicting -- comfortably
  above the >5 non-conflict minimum the code requires to proceed.
- **Gadget search (the actual DMP-activation search over target
  addresses): in progress, not yet converged.** This is GoFetch's own
  inherently trial-and-error step -- trying each non-conflicting eviction
  set against each candidate target address in the dyld/Linux-equivalent
  range, looking for `attack_median - base_median > 50` ticks on 3
  consecutive flush-group trials. One isolated `Get Signal (1)` was
  observed (596 vs. 420 ticks) but did not repeat on the next trial, so it
  reset -- most likely still unmatched (evset, address) noise rather than a
  confirmed leak. The project plan's own risk notes call compound
  eviction-set/gadget search "the hardest engineering piece... most likely
  to take longer than planned" even on the originally-scoped macOS
  platform; that holds here too, compounded by this being a brand new,
  never-before-measured platform with no prior `PP_THRESHOLD` baseline to
  start from (680 was carried over from the Mac's README example purely as
  a starting point, not a calibrated value for this hardware).

### Final result: a real, weak, statistically significant leak

The search did converge. Run 1 (victim launched as `ctswap_victim 1`,
secret fixed at 1 for its whole lifetime): eviction-set generation took
218s, gadget search took 202s, then 100 measurement rounds:

| | predicted "1" | predicted "0" | noisy |
|---|---|---|---|
| **secret=1 victim** (n=100) | 11 | 88 | 1 |

At first glance this looks like a failure -- the correct answer ("1") was
printed only 11% of the time. But rather than stop there, a **control run**
was done: kill the secret=1 victim, launch a fresh `ctswap_victim 0`,
and run the attacker again from scratch (full independent eviction-set +
gadget search, no state reused):

| | predicted "1" | predicted "0" | noisy |
|---|---|---|---|
| **secret=0 victim** (n=100) | 0 | 67 | 33 |

The comparison that matters is "how often does the attacker claim to see a
DMP signal (report '1') under each secret":

```
P(report "1" | secret=1) = 11.0%   95% CI [6.3%, 18.6%]
P(report "1" | secret=0) =  0.0%   95% CI [0.0%, 3.7%]

Two-proportion z-test: z = 3.412, two-sided p = 0.00065
```

The CIs don't overlap, and the difference is significant at p < 0.001. The
false-positive rate is exactly 0% (never claims a signal when the victim's
swap never happens), while the true-positive rate is 11% (low, but clearly
nonzero and clearly distinguishable from the 0% baseline). That's the
correct signature of a **real but weak and uncalibrated** secret-dependent
DMP channel, not a labeling bug or a coincidence -- confirmed by manually
re-deriving the victim's own `mask = (!sk).wrapping_add(1)` swap logic,
which independently confirms "DMP signal present" should correspond to
secret=1, matching the code's own `Secret Key is 1!` branch with no
polarity flip.

**Reproduce:** `python3 phase3/PrimitiveB/analyze_ctswap_linux.py
phase3/PrimitiveB/results/attacker_sk1.log
phase3/PrimitiveB/results/attacker_sk0.log`

**Why only 11%, not ~100% like a calibrated channel should give** (the true
secret-1 condition -- the swap happening, the pointer landing in
`dst_data` -- was present on literally every one of the 100 rounds, so a
perfectly reliable detector would read close to 100%, not 11%):
- `pp_threshold=680` was carried over unchanged from the macOS README's
  example invocation, not calibrated for this hardware/timer at all.
- Each run's gadget search used a different random page offset and a
  different (eviction-set, target-address) pair (confirmed by comparing
  the two runs' logs -- different P+P evset index, different target
  address region) -- gadget quality is not uniform, and the search's own
  bar for declaring success (3 consecutive hits at `repetitions=16`) is
  loose enough to accept a weak gadget.
- The `CounterTimer` cross-core-coherency jitter and DVFS-dependent tick
  rate discussed earlier in this session are both real, uncharacterized
  noise sources specific to this measurement path.

None of that changes the headline finding: this is evidence of **real DMP
data-dependent prefetching activity leaking a secret-dependent pointer
across process boundaries on Asahi Linux**, reproduced end-to-end through
a from-scratch Linux port of GoFetch's own chosen-input attack
architecture -- just at much lower reliability than the paper's own
(calibrated, macOS-native) numbers. Treat the 11%/0% figures as an
*existence proof*, not a figure comparable to GoFetch's reported accuracy.

Artifacts: ported source files listed above;
`phase3/PrimitiveB/analyze_ctswap_linux.py` (analysis script);
`phase3/PrimitiveB/results/` (`attacker_sk{0,1}.log` -- full attacker
stdout for each run, `ctswap_sk{0,1}.txt` -- raw per-round P+P latencies,
`ctswap_bench_sk{0,1}.txt` -- eviction-set-gen/gadget-search timing).
`phase2/GoFetch/poc/crypto_attacker/dyld_space.txt` is generated
per-boot-session (regenerate with `setarch $(uname -m) -R
./target/release/examples/linux_dyld_search` before any future run) and
isn't meant to be committed as a fixed value.
