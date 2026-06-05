from app.core.config import Settings


def test_admin_seed_credentials_are_not_hardcoded(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("ADMIN_DISPLAY_NAME", raising=False)

    settings = Settings(_env_file=None)

    assert settings.ADMIN_EMAIL is None
    assert settings.ADMIN_PASSWORD is None
    assert settings.ADMIN_DISPLAY_NAME is None
