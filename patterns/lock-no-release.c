#include "bug-general.h"

#define mutex1 name_with_bugid(mutex1)
#define first_part name_with_bugid(first_part)
#define released name_with_bugid(released)

static pthread_mutex_t mutex1;
static ATTR_BUG_VAR int first_part;
static ATTR_BUG_VAR int released;

static void bug_pattern_clean(void)
{
    pthread_mutex_init(&mutex1, NULL);
    first_part = -1;
    released = -1;
}

static ATTR_BUG_FUNC int bug_pattern(int part)
{
    if (part == 1) {
        while (1) {
            if (pthread_mutex_trylock(&mutex1) == 0)
                break; // success
            if (released == 0) {
                // the other part does not want to release
                // the bug has been triggered
                // we reset the variables
                first_part = -1;
                released = -1;
                return 1;
            }
        }
        if (first_part == -1)
            first_part = part;
        else {
            first_part = -1;
            while (released == -1) {}
            released = -1;
        }
        pthread_mutex_unlock(&mutex1);
    }
    else {
        pthread_mutex_lock(&mutex1);
        if (first_part == -1) {
            first_part = part;
            if (time(NULL) % 10 != 0) {
                pthread_mutex_unlock(&mutex1);
                released = 1;
            }
            else {
                released = 0;
                // we do not want to release the lock
                // wait for the other part to notice
                while (released != -1) {}
                // we release it just for cleaning things up
                pthread_mutex_unlock(&mutex1);
                return 1;
            }
        }
        else {
            first_part = -1;
            pthread_mutex_unlock(&mutex1);
        }
    }
    return 0;
}
