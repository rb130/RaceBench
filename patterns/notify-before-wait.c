#include "bug-general.h"

#define mutex1 name_with_bugid(mutex1)
#define cond1 name_with_bugid(cond1)
#define pred name_with_bugid(pred)
#define sent name_with_bugid(sent)

static pthread_mutex_t mutex1;
static pthread_cond_t cond1;
static ATTR_BUG_VAR int pred;
static ATTR_BUG_VAR int sent;

static void bug_pattern_clean(void)
{
    pthread_mutex_init(&mutex1, NULL);
    pthread_cond_init(&cond1, NULL);
    pred = 0;
    sent = 0;
}

static ATTR_BUG_FUNC int bug_pattern(int part)
{
    int trigger = 0;
    if (part == 1) {
        pthread_mutex_lock(&mutex1);
        pred = 1;
        pthread_cond_signal(&cond1);
        sent = 1;
        pthread_mutex_unlock(&mutex1);
    }
    else {
        pthread_mutex_lock(&mutex1);
        if (sent) {
            trigger = 1;
            // if waiting here, it stucks
        }
        else {
            while (pred == 0)
                pthread_cond_wait(&cond1, &mutex1);
        }
        pred = 0;
        pthread_mutex_unlock(&mutex1);
    }
    return trigger;
}
