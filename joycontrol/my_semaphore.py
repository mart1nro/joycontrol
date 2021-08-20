import asyncio

class _Request:
    def __init__(self, value, loop):
        self.value = value
        self.future = loop.create_future()


class MySemaphore(asyncio.Semaphore):
    """
    An implementation of the asyncio-Semaphore with a few more features.
    Most this code is copied from the original CPython implementation.
    """
    def __init__(self, value):
        super().__init__(value)
        self._value = value
        self._waiters = [] # Normal people would use an actual Queue. The standard queues are shit
        self._aquired = 0

    def _check_next(self):
        while self._waiters and (self._waiters[0].future.done() or self._value >= self._waiters[0].value):
            r = self._waiters.pop(0)
            if not r.future.done():
                r.future.set_result(None)
                return

    async def acquire(self, count=1):
        if count < 0:
            raise ValueError("Semaphore acquire with count < 0")
        while self._value < count:
            r = _Request(count, self._loop)
            self._waiters.append(r)
            try:
                await r.future
            except:
                r.future.cancel()
                # original has an if here, we wont take the call anymore, call the next one
                self._check_next()
                raise
        self._aquired += count
        self._value -= count
        self._check_next()
        return True

    def reduce(self, value):
        self._value -= value

    def increase(self, value):
        self._value += value
        self._check_next()

    def get_value(self):
        return self._value

    def get_aquired(self):
        return self._aquired

    def release(self, count=1):
        if count < 0:
            raise ValueError("Semaphore release with 0 < count")
        self._value += count
        self._aquired -= count
        self._check_next()

class MyBoundedSemaphore(MySemaphore):
    """
    Äquivalent to asyncio.BoundedSemaphore,
    also with more features
    """
    def __init__(self, limit=1, value=None):
        super().__init__(value if not value is None else limit)
        self._limit = limit

    def get_limit(self):
        return self._limit

    def set_limit(self, value):
        self._limit = value
        self._value = min(self._value, self._limit)

    def release(self, count=1, best_effort=False):
        if self._value + count > self._limit:
            if best_effort:
                count = self._limit - self._value
            else:
                raise ValueError('BoundedSemaphore released too many times')
        super().release(count)
