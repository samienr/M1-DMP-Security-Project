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

## Summary / key takeaways

- **Primitive A (Augury OOB read): reproduced, and beats its own baseline.**
  76.3% pooled accuracy on Linux `clock_gettime`, higher than both this
  project's own macOS run (48.3%) and the paper's own macOS
  `mach_absolute_time` figure (70.2%). Likely explanation: Linux
  `sched_setaffinity` is a hard pin, macOS's QoS-based `pin_cpu()` is only a
  scheduling hint -- plausible but not yet confirmed with a dedicated
  pinned-vs-unpinned control measurement.
- **Primitive B (GoFetch ct-swap): a real but weak secret-dependent DMP
  channel exists on this hardware**, and required a substantial from-scratch
  Linux port (no macOS-only `dyld_search`/`kperf`/QoS APIs survive the
  move). Best measured config: 11% TPR / 0% FPR, p=0.00065 -- statistically
  real, but far below the paper's own macOS numbers.
- **Two independent attempts to improve Primitive B's detection rate both
  failed, and the second made things actively worse.** Lowering the
  classification threshold (50→10) traded a flat TPR for a higher FPR,
  losing significance (p=0.00065→0.096). Raising the search's
  gadget-acceptance bar (3→5 consecutive hits) was worse still: against a
  secret=1 victim it exhausted the *entire* 47-eviction-set search space
  (~51 min) without ever finding a qualifying gadget at all (0% TPR,
  p=1.00, not significant). **Both negative results independently point to
  the same root cause: gadget quality / search-space noise intrinsic to
  this hardware-timer combination, not the final classification threshold
  or the search's acceptance bar.** Neither is a tunable knob here --
  recommend keeping the original 3-hit/threshold-50 configuration as the
  best-known-good baseline, and pursuing the untried levers noted at the
  end of that section (higher `repetitions`, multiple independent searches
  kept-best) only if more time is available.
- **Operational note for future long sessions on this hardware:** this
  machine suspends to `s2idle` on idle/lid-close by default. A multi-hour
  background `ctswap_attacker` search survives a brief suspend/resume
  unharmed (Linux freezes rather than kills processes, and the
  attacker/victim link is loopback TCP, unaffected by network-sleep
  teardown) -- but `systemd-inhibit --what=sleep:idle --mode=block sleep
  infinity` (killed when done) is worth running proactively before kicking
  off any search expected to run past 20-30 minutes, as this session's did.
- **Address-range characterization: independently replicates a published
  Augury finding, not a new discovery (corrected from an earlier,
  overclaimed version of this note).** Ported Augury's `addrs.sh` (never
  run in *this* repo before) and swept `data_buffer`'s forced address
  across 15 orders of magnitude (4 GiB - 128 TiB): zero activation
  anywhere in that range, with activation appearing only in a narrow band
  at the very top of the 48-bit space, binary-searched to an 8 MiB-wide
  transition (~255.9919 TiB). The Augury paper itself already reports
  this exact phenomenon on Asahi Linux (Section VI-B / Table II: "the DMP
  will activate and dereference pointers above `0xffff3f2b0000`, but...
  addresses below `0x280000000` are not dereferenceable") -- our measured
  boundary lands **within ~5.3 GiB of their published `0xffff3f2b0000`**,
  out of a 256,000 GiB range. What's new here is independent replication
  without reference to that number, somewhat tighter precision, and
  explicit confound controls (ruled out AOP-proximity and mapping-overlap)
  the paper doesn't document checking -- not the underlying fact itself.
  See `phase3/AddrRangeSweep/README.md`.

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

## Address-range characterization (Augury's `addrs.sh`, ported) — replicates a published result

**Correction to an earlier version of this section:** this was first
written up as a "genuinely new" finding. It is not -- the Augury paper
itself (Section VI-B, Table II) already reports this exact phenomenon,
tested by the original authors on Asahi Linux: *"we found the DMP to
activate and dereference pointers above `0xffff3f2b0000`, but...
addresses below `0x280000000` are not dereferenceable."* Our
independently-measured boundary (`0xfffded220000`-`0xfffdeda20000`,
~255.9919 TiB) lands within **~5.3 GiB of their published
`0xffff3f2b0000`** (255.997 TiB), out of a 256,000 GiB range -- this is a
replication, not a discovery. The value of this section is the
independent confirmation (we didn't look up their number first), the
finer precision (8 MiB bracket vs. their single reported value), and the
confound checks below that the paper doesn't document -- not the
underlying fact, which was already known and published.

`augury/README.md` lists `addrs.sh` as characterizing DMP behavior "around
`0x280000000-0xffff3f2b0000`" -- whether the DMP's willingness to treat
cached data as a pointer depends on *where* that data lives in the
address space. This was never run in *this repo* before (only the
OOB-read PoC and ct-swap were ported in earlier sessions here).
`addrs.sh` itself
doesn't run on Linux (zsh + conda + a narrow 4-14 GiB default range), but
the underlying C harness (`augury.c`) needed no porting -- it already has
a `#ifdef FORCE_ADDR` path (force-`mmap`'s the pointer-target buffer via
`MAP_FIXED`), and the Linux timer/pin_cpu backing was already in place.

First confirmed the harness activates the DMP at all here, using the
README's own known-good example (`64 3 5 7 16`, unforced): test-pointer
access time dropped from ~270ns to 0-83ns, train time ~16.4us to ~3.8us --
unambiguous. Then swept the forced address log-spaced across 15 orders of
magnitude (4 GiB to 128 TiB, half-bit-exponent steps, `addrs.sh`'s own
`256 1 32 4 1` parameters): **every single point showed zero activation**
(`train_speedup` 0.95-1.04, pure noise, nowhere near the 2.0 success
threshold used by the original tooling's own `get_avg.py`). Two points
near the very top of the 48-bit space (`0xfffeefa00000`, `0xffff81c00000`
-- the same narrow band where this kernel's own *unforced* `mmap(0, ...)`
calls land) showed strong activation (2.84x-4.01x train speedup).
Binary-searched the transition down to an **8 MiB-wide bracket** at
~255.9919 TiB (right at the top of the 48-bit/256 TiB space). Ruled out
two confounds directly: (1) `aop`'s own (ASLR'd, several-GiB-jittery)
address isn't what determines the boundary -- the classification at a
fixed forced address stayed consistent across many independently-ASLR'd
runs; (2) the forced address never overlaps/corrupts `aop`'s own mapping
(confirmed byte ranges don't intersect at one boundary point).

**Conclusion: the DMP's pointer-plausibility heuristic, on this
Linux/Asahi kernel, only recognizes addresses in a narrow band at the very
top of the 48-bit user address space** -- which happens to be exactly
where this kernel's default `mmap` allocator places ordinary unhinted
anonymous mappings, and matches the Augury paper's own published Asahi
Linux boundary to within ~5.3 GiB. A clean independent replication with
tighter precision and documented confound controls, not a new discovery.
Full method, raw sweep data, bisection transcript, and reproduce steps:
`phase3/AddrRangeSweep/README.md`.

## Primitive B (GoFetch ct-swap, Section 5) — ported, run to completion, weak real signal confirmed

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

## Attempt to raise Primitive B's detection rate (both levers tried, neither helped)

Follow-up work, started after the above, to try to improve on the 11%
true-positive rate. Two levers were tried; neither improved on the
original 3-hit/50-threshold configuration, and the second made things
worse. **Current recommendation: keep the original configuration** (11%
TPR / 0% FPR at threshold=50, 3-consecutive-hit bar).

**Lever 1 (tried, confirmed not to help): lower the attack-base diff
threshold.** The attacker's `Secret Key is 1!` classification requires
`attack_median - base_median > 50` (ticks), a magic number hardcoded in
`ctswap_attacker.rs` in two places. A retrospective ROC-style sweep of the
*already-collected* sk0/sk1 round data (full attack/base medians are
printed every round, not just the final verdict, so this needed no new
runs) suggested lowering the cutoff to 10 would raise TPR from 11% to 41%
at the same 0% FPR. That didn't hold up: the threshold was exposed as a
new optional 4th CLI arg (`diff_threshold`, defaults to 50 if omitted, so
old invocations are unaffected) and rebuilt, then tested with two full
fresh runs (new eviction-set-gen + gadget search each, not reusing the
earlier gadget):

| threshold | secret=1 TPR | secret=0 FPR | z | p |
|---|---|---|---|---|
| 50 (original) | 11/100 | 0/100 | 3.412 | **0.00065** (significant) |
| 10 | 10/100 | 4/100 | 1.663 | 0.0963 (not significant) |

Lowering the threshold didn't raise TPR at all (10% vs 11%, noise) and
measurably raised FPR (0%→4%), making the result *less* statistically
distinguishable, not more. A per-run diagnostic (sweeping every possible
threshold against the fresh run's own data) showed why: that run's
attack-base diff distribution was weak noise centered near zero (best
achievable was 51% at threshold=0, decaying fast above it) -- not a clean
bimodal split that any cutoff could cleanly separate. Each run also
independently discovers a *different* (eviction-set, target-address)
gadget via random search, so this retrospective tuning was overfit to one
run's specific noise profile and never had a mechanism to generalize.
**Conclusion: the ceiling here is gadget quality, not the classification
threshold** -- confirmed by direct non-circular testing, not just
inferred.

**Lever 2 (tried to completion, confirmed not to help -- makes things
worse): tighten the gadget-acceptance bar.** The search originally accepts
a gadget after only 3 consecutive `attack_median - base_median >
diff_threshold` hits (`repetitions=16` samples each) -- a loose bar that
two independent search runs both cleared with gadgets that turned out to
carry only weak signal. Raised to 5 consecutive hits in
`ctswap_attacker.rs` (with threshold back at the better-performing 50), on
the reasoning that a stricter bar should reject marginal/lucky gadgets and
keep searching for a more reliably-triggering one, at the cost of a longer
search. An earlier attempt at this run was killed mid-search by a machine
reboot with no result either way; it was resumed and run to completion
against both a secret=1 and a secret=0 victim (fresh eviction-set-gen +
gadget search each, no state reused):

| victim | evset gen | gadget search | outcome |
|---|---|---|---|
| secret=1 | 146s | 3069s (~51 min) | **no gadget found** -- exhausted all 47 non-conflicting eviction sets without any clearing the 5-hit bar |
| secret=0 | 948s (~16 min) | 793s (~13 min) | gadget found at eviction set 11/46, with a clean separation (attack/base medians ~600/~395, a ~200-tick gap vs. the noisy ~20-tick gaps lever 1's gadgets showed) |

Measurement phase (100 rounds each):

| | predicted "1" | predicted "0" | noisy |
|---|---|---|---|
| **secret=1 victim** (n=100) | 0 | 95 | 5 |
| **secret=0 victim** (n=100) | 0 | 100 | 0 |

```
P(report "1" | secret=1) = 0.0%   95% CI [0.0%, 3.7%]
P(report "1" | secret=0) = 0.0%   95% CI [0.0%, 3.7%]

Two-proportion z-test: z = 0.000, two-sided p = 1.00000  (NOT significant)
```

**Reproduce:** `python3 phase3/PrimitiveB/analyze_ctswap_linux.py
phase3/PrimitiveB/results/attacker_sk1_lever2.log
phase3/PrimitiveB/results/attacker_sk0_lever2.log`

Compare to lever 1's p=0.00065 (significant): lever 2 doesn't just fail to
improve things, it destroys the one statistically-significant result this
project had found.

The secret=0 run's 100%-correct, 0-noisy result looks impressive in
isolation, but it is not comparable to lever 1's TPR/FPR table: FPR
(P(report "1" | secret=0)) was *already* 0% under the original 3-hit bar,
so this is not an improvement on the dimension lever 2 was meant to fix.
The dimension that actually mattered -- TPR against a secret=1 victim --
is unambiguously worse under lever 2: the search never found a qualifying
gadget at all across the full 47-evset space, so the measurement phase ran
against an unvalidated fallback address and produced garbage (0% TPR,
worse than lever 1's already-weak 11%).

**Why the asymmetry between the two victims:** the gadget search talks to
the live victim process throughout (not a secret-blind calibration step),
so the search's own success is itself secret-dependent -- whether a given
(eviction-set, target-address) pair produces a clean DMP-triggering signal
depends on where the real swap places the pointer under *that victim's own
fixed secret*. On this hardware, with this timer, at this stricter bar,
a qualifying gadget happened to exist in the available search space for
the secret=0 case and not for the secret=1 case. That is itself useful
information (it says the achievable gadget quality is highly
run-dependent, consistent with lever 1's finding that two independently-
discovered gadgets had very different quality), but it means lever 2's
two runs cannot be read as a paired secret=1-vs-secret=0 comparison of one
fixed gadget -- each run discovers and evaluates its own gadget against
its own victim, same as lever 1.

**Conclusion: lever 2 is a net negative, not just neutral.** Tightening
the acceptance bar does not fix weak-gadget quality; it just makes the
search far more likely to fail outright (51 minutes to scan the entire
non-conflicting-evset space with zero qualifying gadgets, vs. ~200s for
lever 1's 3-hit bar to find *a* gadget, even a weak one) while providing
no guaranteed improvement when it does succeed. **Reverted to the original
3-hit bar** in `ctswap_attacker.rs` (rebuilt) as the best-performing
configuration found so far (11% TPR / 0% FPR, p=0.00065). The real ceiling, confirmed
twice now by two independent, non-circular levers, is gadget quality and
search-space noise intrinsic to this hardware/timer combination, not the
final classification threshold or the search's acceptance bar.

**Other untried levers worth considering for future work:** raising
`repetitions` itself (16 -> 32, matching GoFetch's own README example
value) to shrink per-round variance throughout both the search and
measurement phases; or running several independent full searches (at the
original 3-hit bar) and keeping whichever discovered gadget shows the
cleanest calibration-phase separation, rather than accepting the first one
that clears the acceptance bar.

Artifacts: `phase3/PrimitiveB/results/{attacker_sk0_lever2.log,
attacker_sk1_lever2.log, ctswap_sk0_lever2.txt, ctswap_sk1_lever2.txt,
ctswap_bench_sk0_lever2.txt, ctswap_bench_sk1_lever2.txt}`.

## Why does the paper's ct-swap result look cleaner than ours?

After both tuning levers failed, it's worth directly comparing our
methodology against the GoFetch paper's own (`HW Security Term
Project/usenixsecurity24-chen-boru.pdf`, Section 5, "Attacking
Constant-Time Conditional Swap") rather than just asserting we fall short
of it.

**The paper doesn't actually report a single ct-swap accuracy percentage
either.** Section 5.2 describes running **3200 trials per secret value**
(32x our 100-round measurement) and presents the result qualitatively, as
a "clearly distinguishable" bimodal Prime+Probe latency histogram
(their Figure 9, ~600-800 tick range) -- not a TPR/FPR table. A much
larger sample size makes an aggregate picture look cleaner even without a
better per-trial signal-to-noise ratio; it doesn't by itself mean their
per-trial channel was less noisy than ours, just that they characterized
it with 32x the data we used for our final measurement.

**Checked and ruled out: core pinning.** The code pins the attacker's
main/flush/timer threads to CPU 4-6 and the victim to CPU 7
(`evict-rs/src/lib.rs`, `ctswap_attacker.rs`, `ctswap_victim.rs`). The
original macOS `pin_cpu()` only ever set a QoS class as a scheduling
*hint* (`cpu_id <= 3` -> `QOS_CLASS_BACKGROUND`, `cpu_id <= 7` ->
`QOS_CLASS_USER_INTERACTIVE`), implicitly assuming cores 0-3 are
efficiency cores and 4-7 are performance cores. Verified directly on this
machine via `/proc/device-tree/cpus/cpu@{0..7}/compatible` and
`/sys/.../cpufreq/scaling_max_freq`: cores 0-3 are indeed
`apple,icestorm` (E-cores, 2.064 GHz max) and 4-7 are the Firestorm P-cores
(2.988 GHz max, `compatible` string absent/different, consistent with a
distinct cluster). So the Linux port's hard `sched_setaffinity` pin to
cores 4-7 for all four timing-critical threads is landing them on real
P-cores correctly -- if anything this is a *harder* guarantee than macOS's
own soft QoS hint (same conclusion as the Primitive A pinning finding
above), not a source of extra noise. This was a real hypothesis worth
checking, not just a hand-wave -- it came back negative.

**Most likely real factor (already identified above, restated for
context): uncalibrated thresholds.** `pp_threshold=680` and
`diff_threshold=50` were carried over unchanged from the macOS README's
own example invocation and never independently recalibrated against this
machine's actual Linux/Asahi `CounterTimer` tick-rate and L2 hit/miss
latency distribution. The paper's authors presumably tuned their
equivalent constants for their own test rig; we never ran an equivalent
calibration sweep for Primitive B the way `phase0_skeleton/calibrate.py`
did for Primitive A's PMC-adjacent timing.

**Large, directly-demonstrated run-to-run gadget-quality variance.** This
session's own two lever-2 runs are direct evidence: one random
compound-eviction-set search (secret=0) found a gadget with a clean
~200-tick attack/base separation on its first few tries; a different run
(secret=1, same code, same machine, same boot session) exhausted the
*entire* 47-candidate search space and found nothing usable at all. Lever
1's two independently-discovered gadgets were both weak (10-11% TPR). The
paper's one published Figure 9 is plausibly closer to a best-case draw
from this same quality distribution -- not evidence that every run on
every M1 unit converges this cleanly, or that our port is systematically
inferior for a fixed gadget.

**Still untested, genuinely unknown:** whether Asahi Linux's
reverse-engineered memory-management stack (physical-page allocation
behavior, cache-maintenance op implementations, DVFS governor behavior)
produces "good" compound eviction sets less often than Apple's native
XNU kernel on the same silicon. This would be a legitimate, interesting
Phase-4-style characterization question, but nothing measured so far
isolates it as a cause -- it remains a hypothesis, not a finding.
