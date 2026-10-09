"""Security controls and deployment configuration checks."""
import threading
from collections import defaultdict, deque
from time import monotonic
from urllib.parse import urlparse


PRODUCTION_ENVIRONMENT = "production"
SUPPORTED_ENVIRONMENTS = {"development", PRODUCTION_ENVIRONMENT}
UNSAFE_SECRET_MARKERS = (
    "atlas-local-demo",
    "changeme",
    "password",
    "replace-with",
)


def validate_deployment_config(
    *,
    environment,
    database_url,
    public_url,
    secure_cookies,
    telemetry_api_key,
    bootstrap_admin_password=None,
):
    """Fail fast when an explicitly production-mode process is unsafe.

    Development remains permissive so local SQLite, tests, and the Compose demo
    keep working. These checks protect common configuration boundaries; they do
    not certify a deployment as production ready.
    """
    if environment not in SUPPORTED_ENVIRONMENTS:
        choices = ", ".join(sorted(SUPPORTED_ENVIRONMENTS))
        raise ValueError(f"ATLAS_ENVIRONMENT must be one of: {choices}")
    if environment != PRODUCTION_ENVIRONMENT:
        return

    if not str(database_url).startswith(("postgresql://", "postgresql+")):
        raise RuntimeError("Production mode requires a PostgreSQL DATABASE_URL")
    if not public_url or urlparse(public_url).scheme != "https":
        raise RuntimeError("Production mode requires an HTTPS ATLAS_PUBLIC_URL")
    if not secure_cookies:
        raise RuntimeError("Production mode requires ATLAS_SECURE_COOKIES=1")
    _require_production_secret(
        "ATLAS_TELEMETRY_API_KEY", telemetry_api_key, minimum_length=32
    )
    if bootstrap_admin_password is not None:
        _require_production_secret(
            "ATLAS_BOOTSTRAP_ADMIN_PASSWORD",
            bootstrap_admin_password,
            minimum_length=16,
        )


def _require_production_secret(name, value, minimum_length):
    normalized = (value or "").strip().lower()
    if len(normalized) < minimum_length:
        raise RuntimeError(
            f"Production mode requires {name} with at least {minimum_length} characters"
        )
    if any(marker in normalized for marker in UNSAFE_SECRET_MARKERS):
        raise RuntimeError(f"Production mode rejects demo or placeholder {name}")


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
