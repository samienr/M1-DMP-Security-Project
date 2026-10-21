#ifndef CORE_PIN_H
#define CORE_PIN_H

/* Apple Silicon has no user-space hard core-affinity API (no
 * sched_setaffinity equivalent). The documented way to bias the
 * scheduler toward performance (Firestorm/P-) cores is to raise the
 * thread's QoS class -- this is what Augury (Sec. VI-A1) and GoFetch
 * both rely on. Returns 0 on success. */
int pin_to_performance_core(void);

#endif
