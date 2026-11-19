# Address-range characterization (Augury's `addrs.sh`, ported to Linux)

`augury/README.md` lists `addrs.sh` as the script used to "characterize the
behaviour around `0x280000000-0xffff3f2b0000`" -- i.e. does the M1 DMP's
willingness to treat cached data as a dereferenceable pointer depend on
*where in the virtual address space* that data lives? This was never run
on this Linux/Asahi box in earlier sessions (only the OOB-read PoC and
GoFetch ct-swap were ported). This directory is that experiment, ported
and run here.

`addrs.sh` itself doesn't run on Linux as-is (zsh + conda + a narrow
default sweep of only 4-14 GiB via `make_addrs.py`). The underlying C
harness (`augury/augury.c`) needed no porting at all, though -- it already
has a `#ifdef FORCE_ADDR` path that force-`mmap`s the `data_buffer` (the
array that `aop`'s pointer entries point into) to an attacker-chosen
address via `MAP_FIXED`, and the Linux timer/pin_cpu backing
(`util/linux-util.c`) was already in place from the earlier OOB-read work.

## Sanity check: does the basic harness even work here?

Before trusting any address sweep, confirmed the harness activates the DMP
at all, using the README's own known-good example (`./bin/augury 64 3 5 7
16`, no forced address): test-pointer access time dropped from ~270ns
(baseline) to 0-83ns (AOP on) -- an unambiguous, clean activation. Good,
this hardware/port combination clearly can show the effect; any "no
activation" result below is a real negative, not a broken harness.

## Method

Built `bin/augury` with `FORCEADDR=1` (`-DFORCE_ADDR`), `MACH=1`, native
`gcc` (not the Makefile's default `aarch64-linux-gnu-gcc` cross-compiler
name, same fix as the earlier Primitive A port). Ran it as
`./bin/augury 256 1 32 4 1 <forced_addr>` (`addrs.sh`'s own parameter
choice) across a *log-spaced* sweep of the full 48-bit AArch64 user
address space (`0x100000000` = 4 GiB up to `0x800000000000` = 128 TiB, at
half-bit-exponent steps, all page-aligned), rather than `make_addrs.py`'s
own narrow 4-14 GiB linear default -- the log spacing covers 15 orders of
magnitude for the same number of sample points and is a direct, if
informal, test of the paper's own much larger stated characterization
range.

`train_speedup = baseline_train_mean / aop_train_mean >= 2.0` is the same
success criterion the original `get_avg.py` uses ("was the AOP on?").
`addr_sweep_linux.py` is a from-scratch, stdlib-only re-implementation of
`addrs.sh` + `get_avg.py`'s retry-until-valid orchestration, since this
machine has neither zsh/conda nor numpy/pandas installed.

**One important control:** `data_buffer`'s forced address and `aop`'s own
address (always separately, normally `mmap(0, ...)`-allocated, i.e.
ASLR'd) are independent. Confirmed `aop`'s address varies by several GiB
run-to-run (e.g. `0xfffee2c00000`, `0xffff90800000`, `0xfffeef200000` across
three consecutive unforced runs) while the ON/OFF classification at a
*fixed* forced address stayed perfectly consistent across many separate
process invocations. This rules out "proximity to wherever `aop` happened
to land this run" as the explanation, and rules out the forced address
accidentally overlapping/corrupting `aop`'s own mapping (confirmed
directly for one boundary point: `aop` at `0xfffec2a00000-0xfffec2b02900`,
forced `data_buffer` at `0xfffdeda20000-0xfffe2da20480` -- no overlap).

## Result

**Every single address tested from 4 GiB up through 128 TiB (31 points,
half-bit-exponent log spacing) showed zero DMP activation** --
`train_speedup` pinned at 0.95-1.04 throughout, indistinguishable from
measurement noise, never remotely close to the 2.0 threshold. That's 15
orders of magnitude of the address space with a uniform negative result.

Two points very near the top of the 48-bit space (`0xfffeefa00000`,
`0xffff81c00000` -- addresses in the same narrow band where this kernel's
*own, unforced* `mmap(0, ...)` calls naturally land) showed strong,
unambiguous activation: `train_speedup` 2.84x and 4.01x, `test_speedup`
8.16x and 2.18x.

**Binary-searched the transition** between the last confirmed-OFF point
(`0x800000000000` = 2^47 = 128 TiB) and a confirmed-ON point
(`0xfffeefa00000`), each candidate re-tested, down to an **8 MiB-wide
bracket**: OFF at `0xfffded220000`, ON at `0xfffdeda20000` -- both
~255.9919 TiB, i.e. right at the very top of the 48-bit space (2^48 =
256 TiB exactly). Full transcript in `bisect_boundary_log.txt`.

**A second, unrelated ceiling exists above the activation region:** forcing
addresses at `0xffffa0000000`, `0xfffff0000000`, `0xfffffe000000`, or
`0x1000000000000` (= 2^48, one past the maximum 48-bit address) all failed
outright (`mmap` returning `MAP_FAILED`, or one outright segfault) --
this machine's actual mappable VA ceiling sits somewhere between the
confirmed-good `0xffff81c00000` and `0xffffa0000000`. That's a kernel/ABI
limit (`TASK_SIZE`), not a DMP property, and is a separate fact from the
activation boundary above.

## Interpretation

The DMP's "does this look like a pointer" heuristic (the mechanism
GoFetch's abstract describes as activating on "any cached data that
resembles a pointer") appears to require the candidate value's address to
fall within a narrow band at the very top of the 48-bit AArch64 user
address space -- and, notably, that band is *exactly* where this Linux
kernel's own default top-down `mmap` allocator places ordinary unhinted
anonymous mappings. Whether that's because the DMP's internal
pointer-plausibility check is keyed to a bit-pattern that happens to match
"addresses the OS considers normal," or whether it's some other
address-dependent hardware behavior, isn't something this experiment
isolates -- but the boundary itself is real, sharp (8 MiB out of a
256 TiB space), reproducible across independently-ASLR'd runs, and not an
artifact of the forcing mechanism or of overlapping `aop`'s own mapping.

### Relationship to the published Augury result -- this replicates it, it is not a new discovery

**Correction:** an earlier version of this writeup called this a "new
characterization result... first time this question was tested" on
this machine. That's wrong, and worth flagging explicitly rather than
quietly fixing: the Augury paper (`Augury_Using_Data_Memory-Dependent_
Prefetchers_to_Leak_Data_at_Rest.pdf`, Section VI-B "Memory Addressing
Restrictions", and Table II) already reports this *exact* phenomenon,
and the authors already tested it **on Asahi Linux themselves**:

> "We additionally observed that on MacOS, the DMP will not dereference
> pointers contained in the AoP which have a virtual address between
> `0x280000000` and `0x7fe840004000` -- the end of mappable user-space
> addresses. On Asahi Linux, which allows us to map virtual addresses
> above `0x7fe840004000`, we found the DMP to activate and dereference
> pointers above `0xffff3f2b0000`, but then addresses below
> `0x280000000` are not dereferenceable. At this time, we do not have an
> explanation for why there are restrictions on the virtual addresses the
> M1 DMP will dereference."

Our independently-measured boundary (`0xfffded220000`-`0xfffdeda20000`,
~255.9919 TiB) lands **within ~5.3 GiB of their published
`0xffff3f2b0000`** (255.997 TiB) -- essentially the same number, out of a
256,000 GiB range. We also don't have an explanation for the restriction
(same honest non-conclusion as the paper).

**What's actually new here, then:** independent replication without
having looked up their number first (this project's earlier sessions
hadn't read this part of the PDF closely before running the sweep);
somewhat tighter precision (an 8 MiB bracket via binary search, vs. their
single reported threshold value); and two explicit confound checks the
paper doesn't document doing (ruling out AOP's own ASLR'd address as the
real determinant, and ruling out the forced address overlapping/
corrupting AOP's mapping). The underlying fact about where the M1 DMP
will and won't dereference pointers on Asahi Linux was already known.

## Reproduce

```bash
cd augury
make CC=gcc MACH=1 KEXT=0 FORCEADDR=1 bin/augury
mkdir -p out
python3 addr_sweep_linux.py addrs_sweep3_aligned.dat results.csv   # full log-spaced sweep
python3 bisect_boundary.py                                         # narrows to ~2 GiB
python3 bisect_boundary2.py                                        # narrows to ~8 MiB
```
(`addr_sweep_linux.py`, `bisect_boundary.py`, `bisect_boundary2.py` and
`addrs_sweep3_aligned.dat` here are copies of the same-named files in
`augury/`; the hardcoded `lo`/`hi` brackets in the bisection scripts are
this run's own starting points, not universal constants -- re-derive them
from a fresh sweep if the activation boundary is suspected to differ.)

## Artifacts

- `augury-linux` -- the built `bin/augury` binary (FORCEADDR=1, MACH=1,
  native gcc), for reference/reproduction without rebuilding.
- `sweep_logspaced_aligned.csv` -- the clean, fully page-aligned 31-point
  sweep (4 GiB - 128 TiB, all OFF) plus the two confirmed-ON high points.
- `sweep_logspaced_raw.csv` -- an earlier pass with some non-page-aligned
  sample points (artifacts of an exponent-interpolation bug, not a DMP
  finding); the `FAIL:crashed ... MAP_FAILED` rows in it are alignment
  failures, not address-range characterization data. Kept for the record;
  superseded by the aligned sweep above.
- `bisect_boundary_log.txt` -- full transcript of both bisection passes
  plus the above-the-ON-region failure checks.
- `addr_sweep_linux.py`, `bisect_boundary.py`, `bisect_boundary2.py`,
  `addrs_sweep3_aligned.dat` -- the tooling and address list used.
