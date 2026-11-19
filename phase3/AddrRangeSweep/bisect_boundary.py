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
        # negative result is very consistent, no need to retry much
    return False

lo = 0x800000000000   # confirmed OFF
hi = 0xfffeefa00000   # confirmed ON
print(f"lo=0x{lo:x} OFF (confirmed), hi=0x{hi:x} ON (confirmed)")

PAGE = 0x4000  # 16KiB page alignment required

for i in range(16):
    mid = ((lo + hi) // 2) & ~(PAGE - 1)
    if mid == lo or mid == hi:
        break
    print(f"--- step {i}: testing mid=0x{mid:x} ---")
    result = test_addr(mid)
    if result is None:
        # alignment/mapping issue at this exact point, nudge and retry once
        mid2 = (mid + PAGE) & ~(PAGE - 1)
        print(f"  retrying nudged addr 0x{mid2:x}")
        result = test_addr(mid2)
        if result is None:
            print("  still failing, stopping bisection")
            break
        mid = mid2
    if result:
        hi = mid
    else:
        lo = mid
    print(f"  -> lo=0x{lo:x} hi=0x{hi:x} gap={hi-lo:#x}")

print(f"\nFinal bracket: OFF at 0x{lo:x}, ON at 0x{hi:x}, gap=0x{hi-lo:x} ({(hi-lo)/(1024**3):.2f} GiB)")
