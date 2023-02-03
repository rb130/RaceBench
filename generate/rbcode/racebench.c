#define _GNU_SOURCE
#include "racebench.h"
#include <inttypes.h>
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

uint64_t rb_input_size;
uint8_t *rb_input;
uint8_t rb_triggered = 0;

racebench_statis rb_stat;

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

__attribute__((constructor))
static void racebench_init(int argc, char **argv)
{
    if (argc <= ARG_INPUT) {
        fprintf(stderr, "RaceBench finds no argument %d\n", ARG_INPUT);
        exit(1);
    }
    read_input(argv[ARG_INPUT]);
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

    __sync_fetch_and_add(&rb_stat.total_run, rb_stat_old.total_run);
    for (int i = 0; i < MAX_BUGNUM; ++i) {
        __sync_fetch_and_add(&rb_stat.trigger_num[i], rb_stat_old.trigger_num[i]);
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

void racebench_trigger(int bug_id)
{
    rb_triggered = 1;
    __sync_fetch_and_or(&rb_stat.trigger_num[bug_id], 1);
    // fprintf(stderr, "RaceBench bug %d is triggered.\n", bug_id);
#ifdef EXIT_ONCE_TRIGGER
    racebench_exit();
#endif
}
