#include "core_pin.h"
#include <pthread.h>
#include <stdio.h>

int pin_to_performance_core(void) {
    int rc = pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
    if (rc != 0) {
        perror("[core_pin] pthread_set_qos_class_self_np failed");
        return -1;
    }
    printf("[core_pin] requested QOS_CLASS_USER_INTERACTIVE "
           "(biases scheduling toward P-cores)\n");
    return 0;
}

/* Verification note (do this manually, not in code): run the binary
 * and watch `sudo powermetrics --samplers tasks` or Activity Monitor's
 * CPU history while it's spinning, to confirm it's actually landing on
 * a performance core and not an efficiency core. QoS is a scheduler
 * hint, not a hard guarantee -- if you see it drift to an E-core,
 * that's worth noting as a methodology caveat in your report. */
