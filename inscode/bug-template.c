#include "bug-general.h"

#define __bug_wrap(bug_id) racebench_bug ## bug_id
#define _bug_wrap(bug_id) __bug_wrap(bug_id)
#define bug_wrap _bug_wrap(BUGID)

#define bug_helper name_with_bugid(bug_helper)
#define input_helper name_with_bugid(input_helper)
#define input_helper_init name_with_bugid(input_helper_init)
#define input_check name_with_bugid(input_check)
#define bug_callback name_with_bugid(bug_callback)

static racebench_bug_helper bug_helper;
static racebench_input_helper input_helper;

__attribute__((constructor))
static void input_helper_init(void)
{
    static const uint32_t indices[] = INPUT_INDICES;
    static const uint8_t sizes[] = INPUT_SIZES;
    static const uint32_t pads[] = INPUT_PADS;
    static const uint8_t before_parts[] = BEFORES;
    static const uint32_t mapped_inputs[] = MAPPED_INPUTS;
    static racebench_before_helper before_helpers[INTERLEAVE_NUM] = {};

    input_helper.interleave_num = INTERLEAVE_NUM;
    input_helper.index_num = INDEX_NUM;
    input_helper.indices = indices;
    input_helper.sizes = sizes;
    input_helper.pads = pads;
    input_helper.before_parts = before_parts;
    input_helper.mapped_inputs = mapped_inputs;
    input_helper.before_helpers = before_helpers;
    input_helper.magic_value = MAGIC_VALUE;
}

static int bug_callback(int part)
{
    static racebench_barrier_helper barrier = {};
    if (part == 0) {
        __sync_fetch_and_add(&rb_stat.check_pass_num[BUGID], 1);
        bug_pattern_clean();
    }
    rb_barrier(&barrier);
    return bug_pattern(part);
}

static int input_check(int part)
{
    return rb_input_check(&input_helper, BUGID, part, bug_callback);
}

void bug_wrap(int part)
{
    rb_bug_synchronize(&bug_helper, BUGID, part, input_check);
}