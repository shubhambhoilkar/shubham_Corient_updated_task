"""
Regression tests for the SECRET_KEY handling described in app/__init__.py:_ensure_secret_key.
A hardcoded fallback secret (the previous behaviour) is a real security issue in a
production-oriented app, so this is deliberately covered by tests, not just documentation.
"""
import os

import pytest

from app import create_app
from app.config import Config


class _NoSecretConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


def test_missing_secret_key_raises_in_production(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY is not set"):
        create_app(_NoSecretConfig)


def test_missing_secret_key_warns_but_starts_in_development(monkeypatch, caplog):
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    app = create_app(_NoSecretConfig)
    assert app.config["SECRET_KEY"]  # an ephemeral secret was generated
    assert len(app.config["SECRET_KEY"]) > 20


def test_ephemeral_secrets_differ_between_app_instances(monkeypatch):
    """Each process/instance should get its own random secret, not a shared constant --
    otherwise this degrades right back into a de-facto hardcoded default."""
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    app1 = create_app(_NoSecretConfig)
    app2 = create_app(_NoSecretConfig)
    assert app1.config["SECRET_KEY"] != app2.config["SECRET_KEY"]


def test_explicit_secret_key_is_used_as_is(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "a-real-configured-secret")
    app = create_app(_NoSecretConfig)
    assert app.config["SECRET_KEY"] == "a-real-configured-secret"
