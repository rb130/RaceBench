#include "bug-general.h"

#define __bug_wrap(bug_id) racebench_bug ## bug_id
#define _bug_wrap(bug_id) __bug_wrap(bug_id)
#define bug_wrap _bug_wrap(BUGID)

#define helper name_with_bugid(helper)
#define callback name_with_bugid(callback)

racebench_bug_helper helper;

int callback(int part)
{
    const int indices[INDEX_NUM] = INPUT_INDICES;
    const int sizes[INDEX_NUM] = INPUT_SIZES;
    const unsigned int pads[INTERLEAVE_NUM - INDEX_NUM] = INPUT_PADS;
    const int befores[INTERLEAVE_NUM] = BEFORES;
    static int ptrs[INTERLEAVE_NUM] = {0};

    unsigned int yields = rb_yields[BUGID];

    unsigned int sum = 0;
    for (int i = 0; i < INTERLEAVE_NUM; ++i) {
        unsigned int val;
        if (i < INDEX_NUM) {
            unsigned int mask = ((1u << (sizes[i] * 8 - 1)) - 1) * 2 + 1;
            val = (*(unsigned int*)&rb_input[indices[i]]) & mask;
        }
        else
            val = pads[i - INDEX_NUM];
        sum += val * rb_before(part, befores[i], &ptrs[i], (yields >> i) & 1);
    }

    if (sum == MAGIC_VALUE) {
        static volatile int barrier = 0;
        if (part == 0) {
            bug_pattern_clean();
            __sync_fetch_and_add(&rb_stat.dua_pass_num[BUGID], 1);
            __sync_synchronize();
            barrier = 1;
        }
        else {
            while (!__sync_bool_compare_and_swap(&barrier, 1, 0)) {}
        }

        return bug_pattern(part);
    }
    return 0;
}

void bug_wrap(int part)
{
    rb_bug_synchronize(&helper, BUGID, part, callback);
}