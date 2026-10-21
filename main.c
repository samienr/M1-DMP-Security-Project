#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include "timing.h"
#include "core_pin.h"
#include "evset.h"

/* M1 L2 cache line size per Augury Sec. II-E. Re-measure/confirm this
 * on M4 Pro rather than assuming it carries over. */
#define LINE_SIZE 128
#define POOL_LINES 4096

int main(void) {
    timing_init();
    pin_to_performance_core();

    uint8_t *target = aligned_alloc(LINE_SIZE, LINE_SIZE);
    *(volatile uint8_t *)target = 0;

    /* Baseline: access right after touching it -- should be a cache hit. */
    *(volatile uint8_t *)target;
    uint64_t t0 = now_ns();
    *(volatile uint8_t *)target;
    uint64_t t1 = now_ns();
    uint64_t warm_ns = (t1 - t0) - timer_overhead_ns();
    printf("warm (hit) access latency: %llu ns\n", (unsigned long long)warm_ns);

    evset_t set = evset_build_bruteforce(POOL_LINES, LINE_SIZE);

    /* Try a deliberately loose threshold first; the point of this run
     * is to print a number you can look at and pick a real threshold
     * from, not to get a correct yes/no on the first try. */
    int evicted = evset_evicts(&set, target, warm_ns * 3);
    printf("looks evicted at 3x-warm threshold: %s\n", evicted ? "yes" : "no");
    printf("-> re-run a few times, record the raw t1-t0 values, and pick\n"
           "   a threshold that cleanly separates hit vs. miss before you\n"
           "   trust evset_evicts()'s yes/no.\n");

    evset_free(&set);
    free(target);
    return 0;
}
