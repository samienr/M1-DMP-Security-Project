#include "timing.h"
#include <mach/mach_time.h>
#include <stdio.h>

static mach_timebase_info_data_t g_timebase;
static uint64_t g_overhead_ns = 0;

void timing_init(void) {
    mach_timebase_info(&g_timebase);

    /* Augury/GoFetch both measure timer overhead as back-to-back
     * start/stop in an empty loop and subtract it from later
     * measurements (Augury Sec. V-D). We do the same here. */
    const int trials = 200000;
    uint64_t total_ticks = 0;
    for (int i = 0; i < trials; i++) {
        uint64_t t0 = mach_absolute_time();
        uint64_t t1 = mach_absolute_time();
        total_ticks += (t1 - t0);
    }
    uint64_t avg_ticks = total_ticks / trials;
    g_overhead_ns = (avg_ticks * g_timebase.numer) / g_timebase.denom;

    printf("[timing] timebase numer/denom = %u/%u\n",
           g_timebase.numer, g_timebase.denom);
    printf("[timing] measured mach_absolute_time call overhead: %llu ns\n",
           (unsigned long long)g_overhead_ns);
}

uint64_t now_ns(void) {
    uint64_t t = mach_absolute_time();
    return (t * g_timebase.numer) / g_timebase.denom;
}

uint64_t timer_overhead_ns(void) {
    return g_overhead_ns;
}
