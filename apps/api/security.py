"""Small process-local security controls for the single-worker ATLAS prototype."""
import threading
from collections import defaultdict, deque
from time import monotonic


class LoginRateLimiter:
    def __init__(self, limit=5, window_seconds=300, time_source=monotonic):
        self.limit = limit
        self.window_seconds = window_seconds
        self.time_source = time_source
        self._failures = defaultdict(deque)
        self._lock = threading.Lock()

    def retry_after(self, client_id):
        now = self.time_source()
        with self._lock:
            failures = self._active(client_id, now)
            if len(failures) < self.limit:
                return 0
            return max(1, int(self.window_seconds - (now - failures[0]) + 0.999))

    def failed(self, client_id):
        now = self.time_source()
        with self._lock:
            self._active(client_id, now).append(now)

    def succeeded(self, client_id):
        with self._lock:
            self._failures.pop(client_id, None)

    def _active(self, client_id, now):
        failures = self._failures[client_id]
        cutoff = now - self.window_seconds
        while failures and failures[0] <= cutoff:
            failures.popleft()
        return failures
