#!/bin/bash
# Augury DMP existence — turnkey setup & run for Apple M4 (ECE 382N, Phase 4)
# Mirrors the M1 Phase-0/1 pipeline on a fresh machine. Idempotent.
# Usage:  ./augury_m4_setup.sh [workspace_dir]
set -u
ROOT="${1:-$HOME/Desktop/ece382n-dmp-m4}"
mkdir -p "$ROOT"; cd "$ROOT" || exit 1
echo "==> workspace: $(pwd)"

# 1. Xcode command-line tools
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Installing Xcode CLT — approve the dialog, then re-run this script."
  xcode-select --install; exit 1
fi

# 2. Clone the released Augury tooling (public)
if [ ! -d augury/.git ]; then
  git clone https://github.com/FPSG-UIUC/augury.git augury || { echo "clone FAILED"; exit 1; }
fi
cd augury

# 3. Conda env (lightweight; the repo's pinned augury_env.yml does not resolve on arm64)
source "$(conda info --base)/etc/profile.d/conda.sh" 2>/dev/null || { echo "conda not found"; exit 1; }
conda env list | grep -qE '^augury[[:space:]]' || \
  conda create -n augury -y python=3.10 numpy pandas matplotlib scipy

# 4. Build the mach_absolute_time (KEXT=0) binary
make clean >/dev/null 2>&1
make native KEXT=0 2>&1 | tail -3
[ -x bin/augury ] || { echo "build FAILED"; exit 1; }
echo "    bin/augury built"

# 5. Smoke test on a performance core
#    args: <num_train_ptrs> <offs_past_train_buf> <reps> <coreID> <ptrs_per_cacheline>
mkdir -p out
echo "==> smoke test (train=64, P-core):"
./bin/augury 64 3 5 7 16

cat <<'NOTE'

==> Setup done. To collect data:
  Full existence sweep (Figure-4):   zsh existence.sh         -> existencesweep.csv  (long: 14 sizes x 81 offsets)
  Fast activation check (~2 min):    ./existence_fast.sh      (drop the companion script next to this one)
  One train size, all offsets:       zsh test_sweep.sh myrun 1 <train_size>   -> sweep_out/myrun_1/

==> M4-specific notes:
  * Core pinning is QoS-based, NOT hard core IDs. In util/darwin-util.c, pin_cpu():
      coreID 0-3 -> QOS_CLASS_BACKGROUND      (efficiency / Icestorm-class)
      coreID 4-7 -> QOS_CLASS_USER_INTERACTIVE (performance / Firestorm-class)
    So coreID 4-7 steers to perf cores even though the M4's core count/topology differs
    from M1 - no code change needed. (The binary rejects coreID > 7, so stay within 0-7.)
  * This is genuinely new ground: GoFetch only spot-checked M2/M3, never M4. The Phase-4
    result is the DELTA vs M1 - re-run the same sizes and watch for:
      - whether activation still appears ~train>=3 (or shifts),
      - whether the train=8 dead-zone we saw on M1 reproduces,
      - whether prefetch distance (offset reach) / max speedup changes.
  * For a P-vs-E control, run the same with coreID 2 (Icestorm) -> activation should vanish.
NOTE
