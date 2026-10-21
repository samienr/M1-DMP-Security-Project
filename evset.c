#include "evset.h"
#include "timing.h"
#include <stdlib.h>

evset_t evset_build_bruteforce(size_t pool_lines, size_t line_size) {
    evset_t set;
    set.count = pool_lines;
    set.lines = malloc(pool_lines * sizeof(void *));

    uint8_t *pool = aligned_alloc(line_size, pool_lines * line_size);
    for (size_t i = 0; i < pool_lines; i++) {
        set.lines[i] = pool + i * line_size;
        *(volatile uint8_t *)set.lines[i] = 0; /* fault the page in */
    }
    return set;
}

static void prime(evset_t *set) {
    for (size_t i = 0; i < set->count; i++) {
        *(volatile uint8_t *)set->lines[i];
    }
}

int evset_evicts(evset_t *set, void *target, uint64_t threshold_ns) {
    *(volatile uint8_t *)target; /* warm it */
    prime(set);
    uint64_t t0 = now_ns();
    *(volatile uint8_t *)target;
    uint64_t t1 = now_ns();
    return (t1 - t0 - timer_overhead_ns()) > threshold_ns;
}

void evset_free(evset_t *set) {
    free(set->lines);
    set->lines = NULL;
    set->count = 0;
}
