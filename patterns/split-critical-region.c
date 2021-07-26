#include "bug-general.h"

#define mutex1 name_with_bugid(mutex1)
#define ptr name_with_bugid(ptr)
#define val name_with_bugid(val)

static pthread_mutex_t mutex1;
static ATTR_BUG_VAR int* volatile ptr;
static ATTR_BUG_VAR int val;

static void bug_pattern_clean(void)
{
    pthread_mutex_init(&mutex1, NULL);
    ptr = NULL;
    val = 0;
}

static ATTR_BUG_FUNC int bug_pattern(int part)
{
    int trigger = 0;
    if (part == 1) {
        pthread_mutex_lock(&mutex1);
        //ptr = malloc(sizeof(int));
        ptr = &val;
        pthread_mutex_unlock(&mutex1);
        pthread_mutex_lock(&mutex1);
        //val = *ptr;
        if (ptr == NULL)
            trigger = 1;
        //free((void*)ptr);
        ptr = NULL;
        pthread_mutex_unlock(&mutex1);
    }
    else {
        pthread_mutex_lock(&mutex1);
        //ptr = malloc(sizeof(int));
        ptr = &val;
        //val = *ptr;
        if (ptr == NULL)
            trigger = 1;
        //free((void*)ptr);
        ptr = NULL;
        pthread_mutex_unlock(&mutex1);
    }
    return trigger;
}
