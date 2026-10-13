import threading


class FakeClock:
    """Thread-safe, manually advanced, monotonic clock for tests."""

    def __init__(self, start: float = 1000.0):
        self._now = float(start)
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            return self._now

    def advance(self, seconds: float) -> float:
        if seconds < 0:
            raise ValueError("clock must be monotonic")
        with self._lock:
            self._now += seconds
            return self._now
