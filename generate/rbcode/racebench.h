#ifndef RACE_BENCH_H
#define RACE_BENCH_H

#include <inttypes.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MAX_BUGNUM  {bug_num}
#define ARG_INPUT   {arg_input}

extern uint64_t rb_input_size;
extern uint8_t *rb_input;
extern uint8_t rb_triggered;

typedef struct racebench_statis {
    uint32_t total_run;
    uint32_t trigger_num[MAX_BUGNUM];
} __attribute__((aligned(4),packed)) racebench_statis;

extern racebench_statis rb_stat;

void racebench_trigger(int bugid);

#define EXIT_ONCE_TRIGGER

#ifdef __cplusplus
}
#endif

#endif