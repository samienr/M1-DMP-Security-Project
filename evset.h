#ifndef EVSET_H
#define EVSET_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    void **lines;
    size_t count;
} evset_t;

/* Build a NON-MINIMAL eviction set for `target` by brute force:
 * allocate a large pool of cache-line-sized elements and rely on
 * sheer pool size to thrash the cache. This is a starting point only
 * -- it is NOT the congruent-class-aware construction from Vila et
 * al. [85] that Augury/GoFetch actually use (needed for compound
 * eviction sets and for anything L2-set-targeted). See README.md for
 * what to build next. */
evset_t evset_build_bruteforce(size_t pool_lines, size_t line_size);

/* Primes the set, then times a single access to `target` and reports
 * whether that access exceeded `threshold_ns` (i.e., looked like a
 * cache miss). Calibrate threshold_ns yourself from warm vs. flushed
 * access times on your machine -- don't trust a hardcoded number. */
int evset_evicts(evset_t *set, void *target, uint64_t threshold_ns);

void evset_free(evset_t *set);

#endif
