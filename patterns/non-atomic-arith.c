#include "bug-general.h"

#define arr name_with_bugid(arr)
#define val name_with_bugid(val)
#define pred name_with_bugid(pred)

#define NUM 3
static ATTR_BUG_VAR int arr[NUM];
static ATTR_BUG_VAR int val;
static ATTR_BUG_VAR int pred;

static void bug_pattern_clean(void)
{
    arr[0] = 0, arr[1] = 2, arr[2] = 1;
    val = 0;
    pred = 0;
}

static ATTR_BUG_FUNC int bug_pattern(int part)
{
    int trigger = 0;
    arr[part+1] = 2 - part;
    if (part == 1) {
        for (int i = 0; i < NUM/2; ++i) {
            //__sync_fetch_and_add(&val, arr[i]);
            val += arr[i];
        }
        __sync_synchronize();
        while (!pred)
            pthread_yield();
        trigger = val != NUM;
        pred = 0;
        val = 0;
    }
    else {
        for (int i = NUM/2; i < NUM; ++i) {
            //__sync_fetch_and_add(&val, arr[i]);
            val += arr[i];
        }
        __sync_synchronize();
        pred = 1;
    }
    return trigger;
}
