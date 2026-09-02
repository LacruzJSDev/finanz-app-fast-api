import pytest
from pydantic import ValidationError

from app.config import Settings


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "DATABASE_URL": "postgresql://test:test@localhost/finanzapp_test",
        "SECRET_KEY": "a" * 32,
        "CORS_ALLOWED_ORIGINS": "https://finanzapp.entramaes.com",
        "ENVIRONMENT": "production",
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_production_settings_enable_secure_lax_cookies() -> None:
    settings = make_settings()

    assert settings.cookie_secure is True
    assert settings.cookie_samesite == "lax"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"ENVIRONMENT": "staging"}, "ENVIRONMENT"),
        ({"SECRET_KEY": "too-short"}, "SECRET_KEY"),
        ({"CORS_ALLOWED_ORIGINS": ""}, "CORS_ALLOWED_ORIGINS"),
        ({"CORS_ALLOWED_ORIGINS": "*"}, "orígenes HTTPS exactos"),
        ({"CORS_ALLOWED_ORIGINS": "http://finanzapp.entramaes.com"}, "HTTPS"),
        ({"CORS_ALLOWED_ORIGINS": "https://finanzapp.entramaes.com/app"}, "HTTPS"),
    ],
)
def test_rejects_insecure_production_settings(
    overrides: dict[str, str], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        make_settings(**overrides)


def test_development_allows_local_defaults() -> None:
    settings = make_settings(
        ENVIRONMENT="development", SECRET_KEY="test-secret-key", CORS_ALLOWED_ORIGINS=""
    )

    assert settings.cookie_secure is False
    assert settings.cookie_samesite == "lax"
