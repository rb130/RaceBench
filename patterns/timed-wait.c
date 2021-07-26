#include "bug-general.h"

#define mutex1 name_with_bugid(mutex1)
#define first_part name_with_bugid(first_part)

static pthread_mutex_t mutex1;
static ATTR_BUG_VAR int first_part;

static void bug_pattern_clean(void)
{
    pthread_mutex_init(&mutex1, NULL);
    first_part = -1;
}

static ATTR_BUG_FUNC int bug_pattern(int part)
{
    int trigger = 0;
    if (part == 1) {
        pthread_mutex_lock(&mutex1);
        if (first_part == -1)
            first_part = part;
        else
            first_part = -1;
        pthread_mutex_unlock(&mutex1);
    }
    else {
        usleep(1000);
        pthread_mutex_lock(&mutex1);
        if (first_part == -1) {
            first_part = part;
            trigger = 1;
        }
        else
            first_part = -1;
        pthread_mutex_unlock(&mutex1);
    }
    return trigger;
}
