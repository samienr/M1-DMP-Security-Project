import sys
sys.path.insert(0, '.')
from addr_sweep_linux import run_once

def test_addr(addr):
    for attempt in range(2):
        result, err = run_once(hex(addr))
        if result is None:
            print(f"  0x{addr:x}: FAIL {err}")
            return None
        speedup = result["base_train"] / result["aop_train"]
        print(f"  0x{addr:x}: train_speedup={speedup:.3f}")
        if speedup >= 2.0:
            return True
    return False

lo = 0xfffd6fa30000   # confirmed OFF
hi = 0xfffdefa20000   # confirmed ON
PAGE = 0x4000

for i in range(8):
    mid = ((lo + hi) // 2) & ~(PAGE - 1)
    if mid == lo or mid == hi:
        break
    print(f"--- step {i}: testing mid=0x{mid:x} ---")
    result = test_addr(mid)
    if result is None:
        break
    if result:
        hi = mid
    else:
        lo = mid
    print(f"  -> lo=0x{lo:x} hi=0x{hi:x} gap={(hi-lo)} bytes = {(hi-lo)/(1024**2):.2f} MiB")

print(f"\nFinal: OFF at 0x{lo:x}, ON at 0x{hi:x}, gap={(hi-lo)/(1024**2):.3f} MiB")
