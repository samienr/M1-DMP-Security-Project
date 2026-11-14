#ifndef TIMING_H
#define TIMING_H

#include <stdint.h>

/* Calibrates the mach_absolute_time -> ns conversion and measures
 * timer-call overhead (back-to-back start/stop, averaged). Call once
 * at the start of main(). */
void timing_init(void);

/* Current time in nanoseconds. */
uint64_t now_ns(void);

/* Measured overhead of two back-to-back now_ns() calls, in ns.
 * Subtract this from short intervals before comparing against a
 * hit/miss threshold. */
uint64_t timer_overhead_ns(void);

#endif
