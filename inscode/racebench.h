#ifndef RACE_BENCH_H
#define RACE_BENCH_H

#include <inttypes.h>
#include <pthread.h>

#define MAX_BUGNUM {bug_num}
#define MAX_TRYNUM {try_num}

extern uint64_t rb_input_size;
extern uint8_t *rb_input;
extern uint8_t rb_triggered;

typedef struct racebench_statis {
    uint32_t total_run;
    uint32_t tried_num[MAX_BUGNUM];
    uint32_t dua_pass_num[MAX_BUGNUM];
    uint32_t check_pass_num[MAX_BUGNUM];
    uint32_t trigger_num[MAX_BUGNUM];
} __attribute__((aligned(4),packed)) racebench_statis;

extern racebench_statis rb_stat;

typedef struct racebench_barrier_helper {
    volatile uint8_t var;
    pthread_cond_t cv;
    pthread_mutex_t lock;
} racebench_barrier_helper;

void rb_barrier(racebench_barrier_helper *helper);

typedef struct racebench_before_helper {
    volatile uint8_t before_var;
    racebench_barrier_helper barrier;
} racebench_before_helper;

int rb_before(int part, int bf_part, racebench_before_helper *helper, int yield);

typedef struct racebench_bug_helper {
    uint8_t locks[2];
    uint8_t counter;
    uint8_t success;
    racebench_barrier_helper barrier_before, barrier_after;
} racebench_bug_helper;

void rb_bug_synchronize(racebench_bug_helper *helper, int bugid, int part, int (*callback)(int));

extern unsigned int rb_yields[MAX_BUGNUM];

typedef struct racebench_input_helper {
    uint32_t index_num, interleave_num;
    const uint32_t *indices;
    const uint8_t *sizes;
    const uint32_t *pads;
    const uint8_t *before_parts;
    const uint32_t *mapped_inputs;
    racebench_before_helper *before_helpers;
    uint32_t magic_value;
} racebench_input_helper;

int rb_input_check(racebench_input_helper *helper, int bugid, int part, int (*callback)(int));

uint32_t rb_input_map(uint32_t x);

#endif