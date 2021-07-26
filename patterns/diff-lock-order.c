#include "bug-general.h"

#define mutex1 name_with_bugid(mutex1)
#define mutex2 name_with_bugid(mutex2)

static pthread_mutex_t mutex1;
static pthread_mutex_t mutex2;

static void bug_pattern_clean(void)
{
    pthread_mutex_init(&mutex1, NULL);
    pthread_mutex_init(&mutex2, NULL);
}

static ATTR_BUG_FUNC int bug_pattern(int part)
{
    int trigger = 0;
    if (part == 1) {
        pthread_mutex_lock(&mutex1);
        if (pthread_mutex_trylock(&mutex2) != 0)
            trigger = 1;
        else
            pthread_mutex_unlock(&mutex2);
        pthread_mutex_unlock(&mutex1);
    }
    else {
        pthread_mutex_lock(&mutex2);
        if (pthread_mutex_trylock(&mutex1) != 0)
            trigger = 1;
        else
            pthread_mutex_unlock(&mutex1);
        pthread_mutex_unlock(&mutex2);
    }
    return trigger;
}