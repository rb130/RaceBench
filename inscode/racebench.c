#define _GNU_SOURCE
#include "racebench.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <time.h>
#include <sys/file.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <errno.h>
#include <unistd.h>

#define ARG_INPUT {arg_input}

uint64_t rb_input_size;
uint8_t *rb_input;
uint8_t rb_triggered = 0;

racebench_statis rb_stat;

unsigned int rb_yields[MAX_BUGNUM];

static void read_input(const char *filename)
{
    FILE *file = fopen(filename, "rb");
    if (file == NULL) {
        fprintf(stderr, "RaceBench cannot open %s: %s\n", filename, strerror(errno));
        exit(1);
    }
    fseek(file, 0, SEEK_END);
    rb_input_size = ftell(file);
    fseek(file, 0, SEEK_SET);
    rb_input = (uint8_t*)malloc(rb_input_size);
    fread(rb_input, 1, rb_input_size, file);
    fclose(file);
}

static void setup_yields(void)
{
    int seed = getpid() + time(NULL);
    for (int i = 0; i < MAX_BUGNUM; ++i)
        rb_yields[i] = rand_r(&seed);
}

__attribute__((constructor))
static void racebench_init(int argc, char **argv)
{
    if (argc <= ARG_INPUT) {
        fprintf(stderr, "RaceBench finds no argument %d\n", ARG_INPUT);
        exit(1);
    }
    read_input(argv[ARG_INPUT]);
    setup_yields();

    memset(&rb_stat, 0, sizeof(racebench_statis));
    rb_stat.total_run = 1;
}

static void crash(void)
{
    fprintf(stderr, "RaceBench crashes deliberately.\n");
    abort();
}

static void dump_stats(void)
{
    char *out = getenv("RACEBENCH_STAT");
    if (out == NULL)
        out = ".rb_stat";
    int fd = open(out, O_RDWR | O_CREAT, 0666);
    if (fd == -1) {
        perror("RaceBench cannot open stat file");
        return;
    }
    if (flock(fd, LOCK_EX) == -1) {
        perror("RaceBench fails to lock file");
        return;
    }

    racebench_statis rb_stat_old;
    memset(&rb_stat_old, 0, sizeof(racebench_statis));
    if (read(fd, &rb_stat_old, sizeof(racebench_statis)) == -1) {
        perror("RaceBench read stat file error");
        return;
    }

    rb_stat.total_run += rb_stat_old.total_run;
    for (int i = 0; i < MAX_BUGNUM; ++i) {
        rb_stat.trigger_num[i] += rb_stat_old.trigger_num[i];
        rb_stat.tried_num[i] += rb_stat_old.tried_num[i];
        rb_stat.check_pass_num[i] += rb_stat_old.check_pass_num[i];
        rb_stat.dua_pass_num[i] += rb_stat_old.dua_pass_num[i];
    }

    if (lseek(fd, 0, SEEK_SET) == -1) {
        perror("RaceBench lseek error");
        return;
    }
    if (write(fd, &rb_stat, sizeof(racebench_statis)) == -1) {
        perror("RaceBench write stat file error");
        return;
    }

    if (flock(fd, LOCK_UN) == -1) {
        perror("RaceBench fails to unlock file");
        return;
    }

    close(fd);
}

__attribute__((destructor))
static void racebench_exit(void)
{
    dump_stats();
    if (rb_triggered > 0)
        crash();
}

static int p_before(volatile uint8_t *ptr, int part, int bf_part)
{
    if (__sync_fetch_and_or(ptr, 1<<part) == 0) {
        return part == bf_part;
    }
    else {
        *ptr = 0;
        return part != bf_part;
    }
}

void rb_barrier(racebench_barrier_helper *helper)
{
    volatile uint8_t *ptr = &helper->var;
    pthread_mutex_lock(&helper->lock);
    int cleaner = (*ptr)++ == 0;
    if (cleaner) {
        while (*ptr != 2)
            pthread_cond_wait(&helper->cv, &helper->lock);
        *ptr = 0;
    }
    else {
        pthread_cond_signal(&helper->cv);
    }
    pthread_mutex_unlock(&helper->lock);
}

int rb_before(int part, int bf_part, racebench_before_helper *helper, int yield)
{
    rb_barrier(&helper->barrier);
    if ((yield & 1) == part)
        pthread_yield();
    return p_before(&helper->before_var, part, bf_part);
}

void rb_bug_synchronize(racebench_bug_helper *helper, int bugid, int part, int (*callback)(int))
{
    volatile uint8_t *plock = &helper->locks[part];
    volatile uint8_t *pcnt = &helper->counter;
    volatile uint8_t *succ = &helper->success;

    if (rb_stat.tried_num[bugid] >= MAX_TRYNUM)
        return;

    if (!__sync_bool_compare_and_swap(plock, 0, 1))
        return;

    uint8_t ok = 0;
    if (__sync_fetch_and_add(pcnt, 1) == 1)
        ok = 1;
    else {
        // wait a moment for the other part?
        // pthread_yield();
        if (!__sync_bool_compare_and_swap(pcnt, 1, 0))
            ok = 1;
    }

    if (ok) {
        if (part == 1)
            __sync_fetch_and_add(&rb_stat.tried_num[bugid], 1);

        rb_barrier(&helper->barrier_before);
        __sync_fetch_and_add(pcnt, -1);
        if (callback(part))
            __sync_fetch_and_or(succ, 1);
        rb_barrier(&helper->barrier_after);

        /* statistics */
        if (__sync_bool_compare_and_swap(succ, 1, 0)) {
            __sync_fetch_and_add(&rb_stat.trigger_num[bugid], 1);
            __sync_fetch_and_or(&rb_triggered, 1);
        }
    }

    __sync_fetch_and_add(plock, -1);
}

int rb_input_check(racebench_input_helper *helper, int bugid, int part, int (*callback)(int))
{
    uint32_t num_max;
    if (helper->index_num < helper->interleave_num)
        num_max = helper->interleave_num;
    else
        num_max = helper->index_num;

    uint32_t yields = rb_yields[bugid];
    uint8_t correct_input = 1;
    uint32_t sum = 0;

    for (uint32_t i = 0; i < num_max; ++i) {
        uint32_t val = 0;
        if (i < helper->index_num) {
            uint32_t mask = ((1u << (helper->sizes[i] * 8 - 1)) - 1) * 2 + 1;
            if (helper->indices[i] < rb_input_size) {
                val = (*(uint32_t*)&rb_input[helper->indices[i]]) & mask;
                val = rb_input_map(val);
            }
            correct_input = (correct_input && val == helper->mapped_inputs[i]);
        }
        else
            val = helper->pads[i - helper->index_num];

        int is_before;
        if (i < helper->interleave_num)
            is_before = rb_before(part, helper->before_parts[i], &helper->before_helpers[i], (yields >> i) & 1);
        else
            is_before = 1;
        sum += val * is_before;
    }

    if (part == 0)
        __sync_fetch_and_add(&rb_stat.dua_pass_num[bugid], correct_input);
    if (sum == helper->magic_value)
        return callback(part);
    return 0;
}

uint32_t rb_input_map(uint32_t x)
{
    x ^= 0xda017281;
    x += 0x10101014;
    x = (x << 4) | ((x >> 28) & 0xf);
    return x;
}