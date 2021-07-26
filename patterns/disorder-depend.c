#include "bug-general.h"

#define ok name_with_bugid(ok)
#define ptr name_with_bugid(ptr)
#define val name_with_bugid(val)

static ATTR_BUG_VAR int ok;
static ATTR_BUG_VAR int* volatile ptr;
static ATTR_BUG_VAR int val;

static void bug_pattern_clean(void)
{
    ok = 0;
    ptr = NULL;
    val = 0;
}

static ATTR_BUG_FUNC int bug_pattern(int part)
{
    int trigger = 0;
    if (part == 1) {
        /* disordered instructions:
         * ptr = &val;
         * ok = 1;
         */
        ok = 1;
        __sync_synchronize();
        ptr = &val;
    }
    else {
        while (!ok)
            pthread_yield();
        // val = *ptr;
        if (ptr == NULL)
            trigger = 1;
        ptr = NULL;
        ok = 0;
    }
    return trigger;
}
