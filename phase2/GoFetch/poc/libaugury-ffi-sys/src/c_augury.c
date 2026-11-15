#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <assert.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#ifndef __APPLE__
#include <sched.h>
#include <sys/resource.h>
#endif

#include "c_augury.h"

#define MSB_MASK 0x8000000000000000

#ifdef __APPLE__
// macOS: real high-resolution monotonic clock, via clock_gettime_nsec_np.
// The zero_dependency param/ns_ptr-offset dance is purely to stop the
// compiler from treating consecutive timer reads as redundant/hoistable --
// zero_dependency is always numerically 0 once truncated to int32_t (it's
// derived from a uint64_t top-bit mask), but it's *data-dependent* 0, so it
// can't be constant-folded away.
uint64_t (*ns_ptr)(clockid_t) = &clock_gettime_nsec_np;

uint64_t get_time_nano(int32_t zero_dependency)
{
    /* MEM_BARRIER; */
	uint64_t t = zero_dependency;
	/* t += mach_absolute_time(); */
    t += (*(ns_ptr + zero_dependency))(CLOCK_UPTIME_RAW);
	/* t += READ_TIMER; */
    /* MEM_BARRIER; */
	return t;
}
#else
// Non-macOS (Asahi Linux on the same M1): no clock_gettime_nsec_np, so use
// clock_gettime(CLOCK_MONOTONIC) instead -- same timer source already used
// by augury/util/linux-util.c's get_time_nano() for Primitive A. Keep the
// same data-dependent zero_dependency trick (fed into tv_nsec before the
// call) so the compiler still can't treat this as a pure/cacheable read.
uint64_t get_time_nano(int32_t zero_dependency)
{
	struct timespec ts;
	ts.tv_nsec = zero_dependency;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return 1000000000ULL * (uint64_t)ts.tv_sec + (uint64_t)ts.tv_nsec;
}
#endif // __APPLE__

#ifdef __APPLE__
void pin_cpu(size_t core_no)
{
	if (core_no <= 3) { // ICESTORM
		pthread_set_qos_class_self_np(QOS_CLASS_BACKGROUND, 0);
	} else if (core_no <= 7) { // FIRESTORM
		pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
	} else {
		assert(0 && "error! make sure 0 <= core_no <= 7");
	}
}
#else
// Non-macOS: there's no QOS class API, so pin directly to the requested
// core via sched_setaffinity, same approach as augury/util/linux-util.c's
// pin_cpu(). core_no is still expected to name a specific core (0-7 on this
// M1 under Asahi), not just an E/P-core *class* as the macOS QOS call does.
void pin_cpu(size_t core_no)
{
	cpu_set_t set;
	CPU_ZERO(&set);
	CPU_SET(core_no, &set);
	if (sched_setaffinity(0, sizeof(cpu_set_t), &set) < 0) {
		perror("pin_cpu: sched_setaffinity");
		exit(EXIT_FAILURE);
	}
	// Favor this process in the scheduler to cut preemption-induced noise
	// in the P+P timing loop (same as linux-util.c).
	setpriority(PRIO_PROCESS, 0, -20);
}
#endif // __APPLE__

uint64_t c_sleep(uint64_t duration, uint64_t __trash)
{
    uint64_t T1 = 0, T2 = 0;
    uint64_t train_time;
    uint64_t base = 1;

    T1 = get_time_nano(__trash & MSB_MASK);

    __trash = (__trash + T1) & MSB_MASK;

    do
    {
        T2 = get_time_nano(__trash & MSB_MASK);
        train_time = (T2 - T1) | (__trash & MSB_MASK);
        
        uint64_t count = 0;
        do
        {
            count += base | (__trash & MSB_MASK);
        } while(count < 9999);
    } while(train_time < duration);

    return train_time;
}

uint64_t c_thrash_cache(uint64_t* thrash_addr, \
    uint32_t size_of_thrash_array, uint64_t __trash)
{
    volatile uint64_t *thrash_arr = thrash_addr;

    for (uint32_t j = 0; j < size_of_thrash_array / sizeof(uint64_t) - 2;
            j++) {
        __trash += (thrash_arr[j] ^ __trash) & 0b1111;
        __trash += (thrash_arr[j + 1] ^ __trash) & 0b1111;
        __trash += (thrash_arr[j + 2] ^ __trash) & 0b1111;
    }
    return __trash;
}

uint64_t flush_evset(uint64_t* evset_start, uint32_t num_of_ptrs)
{
    // Not a Linux-specific issue: the original cast was to a non-volatile
    // `uint64_t**`, which is an incompatible-pointer-types mismatch against
    // the `volatile uint64_t**` it's assigned to. Older/default-mode GCC
    // only warned about this; GCC 14+'s C defaults (what this machine's
    // toolchain uses) make it a hard error, which only showed up now
    // because cargo's `cc` crate invokes the compiler with `-Wall -Wextra`
    // (the plain `make`-built augury/GoFetch C targets don't, so this was
    // latent there too). Fixed by casting through the correctly-qualified
    // pointer type instead of suppressing the check.
    volatile uint64_t **aop = (volatile uint64_t**)evset_start;
    uint64_t __trash = 0;
    for (uint32_t j = 0; j < num_of_ptrs; j++) {
        __trash = *aop[j % num_of_ptrs];
        __trash = *aop[(j+1) % num_of_ptrs];
        __trash = *aop[(j+2) % num_of_ptrs];
        __trash = *aop[(j+3) % num_of_ptrs];
        __trash = *aop[(j+4) % num_of_ptrs];
        __trash = *aop[(j+5) % num_of_ptrs];
        __trash = *aop[(j+6) % num_of_ptrs];
        __trash = *aop[(j+7) % num_of_ptrs];
        __trash = *aop[(j+8) % num_of_ptrs];
        __trash = *aop[(j+9) % num_of_ptrs];
        __trash = *aop[(j+10) % num_of_ptrs];
        __trash = *aop[(j+11) % num_of_ptrs];
        __trash = *aop[(j+12) % num_of_ptrs];
    }
    return __trash;
}

// openssl constant-time swap for uint64
void constant_time_cond_swap_64(uint64_t mask, uint64_t *a,
                                uint64_t *b)
{
    uint64_t xor = *a ^ *b;

    xor &= mask;
    *a ^= xor;
    *b ^= xor;
}