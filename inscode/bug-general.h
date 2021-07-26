#ifndef RB_BUG_GENERAL_H
#define RB_BUG_GENERAL_H

#ifndef BUGID
#error "BUGID is not defined."
#endif

#define __name_with_bugid(name, bugid) _bug ## bugid ## _ ## name
#define _name_with_bugid(name, bugid) __name_with_bugid(name, bugid)
#define name_with_bugid(name) _name_with_bugid(name, BUGID)

#define ATTR_BUG_VAR  volatile __attribute__((used))
#if defined(__clang__)
#define ATTR_BUG_FUNC __attribute__((optnone))
#elif defined(__GNUC__)
#define ATTR_BUG_FUNC __attribute__((optimize(0)))
#endif

#define bug_pattern name_with_bugid(pattern)
#define bug_pattern_clean name_with_bugid(pattern_clean)

static void bug_pattern_clean(void);
static int bug_pattern(int part);

#endif