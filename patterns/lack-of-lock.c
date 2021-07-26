#include "bug-general.h"

#define mutex1 name_with_bugid(mutex1)
#define val name_with_bugid(val)

static pthread_mutex_t mutex1;
static ATTR_BUG_VAR int val;

static void bug_pattern_clean(void)
{
    pthread_mutex_init(&mutex1, NULL);
    val = 0;
}

static ATTR_BUG_FUNC int bug_pattern(int part)
{
    int trigger = 0;
    volatile int *ptr = &val;
    if (part == 1) {
        pthread_mutex_lock(&mutex1);
        int new_val = *ptr + 1;
        *ptr = new_val;
        __sync_synchronize();
        if (*ptr != new_val)
            trigger = 1;
        pthread_mutex_unlock(&mutex1);
    }
    else {
        int new_val = *ptr + 1;
        *ptr = new_val;
        __sync_synchronize();
        if (*ptr != new_val)
            trigger = 1;
    }
    return trigger;
}
