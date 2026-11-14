#!/bin/bash
# Fast existence check — activating train sizes x a few offsets, reads test-access
# speedup directly from out/aop.out vs out/baseline.out (outlier-trimmed).
# Place next to augury_m4_setup.sh's cloned augury/ dir and run from inside augury/.
cd "$(dirname "$0")"
CORE=7; REPS=32; DENSITY=16
mkdir -p out
echo "train,offset,aop_test_ns,baseline_test_ns,speedup"
for train in 4 8 16 64 256 1024; do
  for offs in 1 2 3 5 10; do
    ./bin/augury $train $offs $REPS $CORE $DENSITY >/dev/null 2>&1
    python3 - "$train" "$offs" <<'PY'
import sys,statistics as s
train,offs=sys.argv[1],sys.argv[2]
def m(fn):
    v=[]
    for l in open(fn):
        l=l.strip()
        if not l or l.startswith("0x") or l.startswith("test"): continue
        try: v.append(float(l.split(",")[0]))
        except: pass
    v=[x for x in v if x<1500]
    return s.mean(v) if v else float("nan")
try:
    a=m("out/aop.out"); b=m("out/baseline.out")
    print(f"{train},{offs},{a:.0f},{b:.0f},{b/a:.2f}")
except Exception as e:
    print(f"{train},{offs},ERR,ERR,{e}")
PY
  done
done
