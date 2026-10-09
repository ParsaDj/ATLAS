import pytest

from apps.api.security import validate_deployment_config


VALID = {
    "environment": "production",
    "database_url": "postgresql+psycopg://atlas@db/atlas",
    "public_url": "https://atlas.example.com",
    "secure_cookies": True,
    "telemetry_api_key": "bridge-key-7c1d9e3f5a8b2c4d6e0f1a3b",
    "bootstrap_admin_password": "admin-secret-7c1d9e3f5a8b",
}


def validate(**overrides):
    config = VALID | overrides
    validate_deployment_config(**config)


def test_development_mode_keeps_local_configuration_available():
    validate_deployment_config(
        environment="development",
        database_url="sqlite:///atlas.db",
        public_url=None,
        secure_cookies=False,
        telemetry_api_key=None,
    )


def test_production_mode_accepts_guarded_configuration():
    validate()


@pytest.mark.parametrize("environment", ["prod", "staging", "PRODUCTION"])
def test_unknown_environment_is_rejected(environment):
    with pytest.raises(ValueError, match="ATLAS_ENVIRONMENT"):
        validate(environment=environment)


def test_production_mode_requires_postgresql():
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        validate(database_url="sqlite:///atlas.db")


@pytest.mark.parametrize("public_url", [None, "http://atlas.example.com"])
def test_production_mode_requires_public_https(public_url):
    with pytest.raises(RuntimeError, match="HTTPS ATLAS_PUBLIC_URL"):
        validate(public_url=public_url)


def test_production_mode_requires_secure_cookies():
    with pytest.raises(RuntimeError, match="ATLAS_SECURE_COOKIES=1"):
        validate(secure_cookies=False)


@pytest.mark.parametrize(
    "telemetry_api_key",
    [None, "too-short", "atlas-local-demo-bridge-key-123456789"],
)
def test_production_mode_rejects_missing_or_demo_bridge_secrets(telemetry_api_key):
    with pytest.raises(RuntimeError, match="ATLAS_TELEMETRY_API_KEY"):
        validate(telemetry_api_key=telemetry_api_key)


@pytest.mark.parametrize(
    "bootstrap_admin_password",
    ["short", "replace-with-a-long-production-secret"],
)
def test_production_mode_rejects_unsafe_bootstrap_passwords(
    bootstrap_admin_password,
):
    with pytest.raises(RuntimeError, match="ATLAS_BOOTSTRAP_ADMIN_PASSWORD"):
        validate(bootstrap_admin_password=bootstrap_admin_password)


def test_production_mode_allows_bootstrap_secret_to_be_omitted():
    validate(bootstrap_admin_password=None)
