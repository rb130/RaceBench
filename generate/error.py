class BugError(Exception):
    pass


class BugNoPosition(BugError):
    pass


class BugCantTrigger(BugError):
    pass


class InjectError(BugError):
    pass


class NoAvailableVariable(BugError):
    pass


class BugTooEasy(BugError):
    pass


class CantFollowOrder(BugError):
    pass


class CantReproduce(BugError):
    pass


class LockError(BugError):
    pass
