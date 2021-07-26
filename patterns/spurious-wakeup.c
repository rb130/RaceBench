#include "bug-general.h"

#define mutex1 name_with_bugid(mutex1)
#define cond1 name_with_bugid(cond1)
#define pred name_with_bugid(pred)
#define ptr name_with_bugid(ptr)
#define val name_with_bugid(val)

static pthread_mutex_t mutex1;
static pthread_cond_t cond1;
static ATTR_BUG_VAR int* volatile ptr;
static ATTR_BUG_VAR int val;
static ATTR_BUG_VAR int pred;

static void bug_pattern_clean(void)
{
    pthread_mutex_init(&mutex1, NULL);
    pthread_cond_init(&cond1, NULL);
    ptr = NULL;
    val = 0;
    pred = 0;
}

static ATTR_BUG_FUNC int bug_pattern(int part)
{
    int trigger = 0;
    if (part == 1) {
        pred = 0;
        pthread_cond_signal(&cond1);
        pthread_mutex_lock(&mutex1);
        //ptr = malloc(sizeof(int));
        ptr = &val;
        pred = 1;
        pthread_mutex_unlock(&mutex1);
        pthread_cond_signal(&cond1);
    }
    else {
        pthread_mutex_lock(&mutex1);
        if (!pred)
            pthread_cond_wait(&cond1, &mutex1);
        //val = *ptr;
        if (ptr == NULL)
            trigger = 1;
        //free((void*)ptr);
        ptr = NULL;
        pred = 0;
        pthread_mutex_unlock(&mutex1);
    }
    return trigger;
}
