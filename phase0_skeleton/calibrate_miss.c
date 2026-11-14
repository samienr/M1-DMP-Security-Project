/* calibrate_miss.c
 *
 * Standalone companion to phase0_skeleton -- does NOT modify main.c,
 * evset.c, or the Makefile. Reuses timing.c/core_pin.c as-is and adds
 * the "guaranteed-miss latency" measurement phase0_skeleton doesn't
 * print on its own.
 *
 * v2 changes, after the first calibration run showed warm/miss
 * distributions overlapping (miss sometimes as fast as warm):
 *
 *   1. A full barrier (dsb sy + isb) is now issued between the flush
 *      loop and the timed access. Without it, the core can execute the
 *      timed load out of program order -- speculatively satisfying it
 *      while the flush loop above is still retiring -- which hides the
 *      eviction's cost and reports a near-hit latency even when the
 *      flush did its job. This is the same reason Prime+Probe code in
 *      Augury/GoFetch-style PoCs uses serializing instructions around
 *      the timed region.
 *   2. Each run now takes many internal trials (default 51) and
 *      reports their median, instead of a single flush+time sample.
 *      This absorbs ordinary scheduling/timer noise within one process
 *      launch; calibrate.py still launches this binary N times on top
 *      of that, for across-process variation.
 *   3. A diagnostic counts trials whose latency falls well below the
 *      run's own median -- a rough signal that the flush failed to
 *      evict `target` that particular trial (e.g. because the linear
 *      virtual sweep didn't happen to cover target's physical cache
 *      set), as distinct from ordinary timer jitter. This does NOT fix
 *      that failure mode -- a real fix is the congruent-class eviction
 *      set construction the README already flags as needed for Phase 1
 *      -- it only tells you whether it's happening and how often.
 *
 * Build (no Makefile edits needed -- calibrate.py does this for you):
 *   clang -O0 -Wall -Wextra -c timing.c core_pin.c
 *   clang -O0 -Wall -Wextra -o calibrate_miss calibrate_miss.c timing.o core_pin.o
 *
 * Usage:
 *   ./calibrate_miss [num_trials]   (default 51)
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include "timing.h"
#include "core_pin.h"

#define LINE_SIZE 128                     /* matches main.c's LINE_SIZE */
#define FLUSH_BYTES (64UL * 1024 * 1024)  /* well past M1/M4 Pro L2 */
#define DEFAULT_TRIALS 51

static int cmp_u64(const void *a, const void *b) {
    uint64_t x = *(const uint64_t *)a, y = *(const uint64_t *)b;
    return (x > y) - (x < y);
}

/* Full system data-memory barrier + instruction-sync barrier. Forces
 * the core to finish all outstanding memory accesses from the flush
 * loop, and to not begin executing the subsequent timed load, until
 * this point -- closing the speculative-reordering gap described
 * above. AArch64 instructions, valid on Apple Silicon. */
static inline void full_barrier(void) {
    __asm__ __volatile__("dsb sy" ::: "memory");
    __asm__ __volatile__("isb" ::: "memory");
}

int main(int argc, char **argv) {
    int trials = DEFAULT_TRIALS;
    if (argc > 1) {
        int parsed = atoi(argv[1]);
        if (parsed > 0) trials = parsed;
    }

    timing_init();
    pin_to_performance_core();

    uint8_t *target = aligned_alloc(LINE_SIZE, LINE_SIZE);
    *(volatile uint8_t *)target = 0;
    *(volatile uint8_t *)target; /* warm it once before the first trial */

    uint8_t *flush_buf = malloc(FLUSH_BYTES);
    if (!flush_buf) {
        fprintf(stderr, "[calibrate_miss] failed to allocate %lu-byte flush buffer\n",
                FLUSH_BYTES);
        free(target);
        return 1;
    }
    /* Touch every page once up front so first-touch faults don't land
     * inside a timed trial below. */
    for (size_t i = 0; i < FLUSH_BYTES; i += LINE_SIZE) {
        flush_buf[i] = 1;
    }

    uint64_t *samples = malloc((size_t)trials * sizeof(uint64_t));
    if (!samples) {
        fprintf(stderr, "[calibrate_miss] failed to allocate samples array\n");
        free(flush_buf);
        free(target);
        return 1;
    }

    for (int t = 0; t < trials; t++) {
        /* Evict target by re-streaming the flush buffer. Each trial
         * re-evicts from whatever state the previous trial's timed
         * access left target in -- no need to re-warm explicitly. */
        for (size_t i = 0; i < FLUSH_BYTES; i += LINE_SIZE) {
            *(volatile uint8_t *)(flush_buf + i) += 1;
        }

        full_barrier();

        uint64_t t0 = now_ns();
        *(volatile uint8_t *)target;
        uint64_t t1 = now_ns();

        samples[t] = (t1 - t0) - timer_overhead_ns();
    }

    qsort(samples, (size_t)trials, sizeof(uint64_t), cmp_u64);
    uint64_t min_v = samples[0];
    uint64_t max_v = samples[trials - 1];
    uint64_t median_v = samples[trials / 2];

    uint64_t sum = 0;
    for (int t = 0; t < trials; t++) sum += samples[t];
    uint64_t mean_v = sum / (uint64_t)trials;

    /* Rough diagnostic, not a hard rule: a trial whose latency is less
     * than half the run's own median is suspicious -- flag it as a
     * likely failed eviction rather than silently folding it into the
     * median. */
    int likely_failed = 0;
    for (int t = 0; t < trials; t++) {
        if (samples[t] < median_v / 2) likely_failed++;
    }

    printf("miss (evicted) access latency: %llu ns\n", (unsigned long long)median_v);
    printf("  [calibrate_miss internal] n=%d min=%llu median=%llu mean=%llu max=%llu "
           "likely-failed-evictions=%d/%d\n",
           trials, (unsigned long long)min_v, (unsigned long long)median_v,
           (unsigned long long)mean_v, (unsigned long long)max_v,
           likely_failed, trials);

    if (likely_failed > trials / 10) {
        fprintf(stderr,
                "[calibrate_miss] WARNING: %d/%d trials in this run look like failed "
                "evictions (latency far below this run's own median). If this persists "
                "after the barrier fix, it's most likely the linear virtual sweep not "
                "covering target's physical cache set every time -- the README's note "
                "on evset_build_bruteforce needing a congruent-class construction for "
                "anything set-targeted applies here too. Treat this run's number as "
                "optimistic until that's addressed.\n",
                likely_failed, trials);
    }

    free(samples);
    free(flush_buf);
    free(target);
    return 0;
}
