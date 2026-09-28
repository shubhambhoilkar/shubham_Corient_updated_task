import os
import secrets

from flask import Flask

from app.config import Config
from app.extensions import db
from app.utils.logging import configure_logging, get_logger


def create_app(config_object: type = Config) -> Flask:
    configure_logging()
    logger = get_logger("epi.startup")

    app = Flask(__name__)
    app.config.from_object(config_object)

    _ensure_secret_key(app, logger)

    fixtures_dir = app.config.get("FIXTURES_DIR")
    if fixtures_dir and not os.path.isdir(fixtures_dir):
        logger.warning(
            "FIXTURES_DIR does not exist -- fixture-mode searches will return zero "
            "results from every source until this is fixed",
            extra={"ctx": {"fixtures_dir": fixtures_dir}},
        )

    db.init_app(app)

    from app.api.routes import api_bp
    from app.web.routes import web_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)

    with app.app_context():
        db.create_all()

    return app


def _ensure_secret_key(app: Flask, logger) -> None:
    """No hardcoded fallback secret is allowed in Config (see app/config.py). This is where
    the two acceptable outcomes of a missing SECRET_KEY are enforced instead:
      - production (FLASK_ENV=production): refuse to start. A production app running with
        no secret, or with everyone's-repo's-same default secret, can have its session
        cookies forged; failing loudly at boot is the correct behaviour, not a warning
        that's easy to miss in a log stream.
      - anything else (local dev, tests): generate a random, process-local secret and warn
        clearly. This keeps `python run.py` and `pytest` working with zero setup, at the
        cost of signed sessions not surviving a restart -- which is fine for development
        and is exactly what the warning says.
    """
    # Read the environment fresh here rather than trusting app.config["SECRET_KEY"] alone:
    # Config.SECRET_KEY is `os.getenv("SECRET_KEY")` evaluated once, the moment app.config is
    # first imported. That's fine for a real process (imported once, right before use), but
    # it means a config *class* attribute can be stale relative to the environment by the
    # time create_app() actually runs (e.g. under a test runner that imports the module once
    # and then exercises many different env-var scenarios against it). Reading os.environ
    # directly here keeps this function correct regardless of when Config was imported.
    secret = os.getenv("SECRET_KEY") or app.config.get("SECRET_KEY")
    if secret:
        app.config["SECRET_KEY"] = secret
        return

    env = os.getenv("FLASK_ENV", "development").strip().lower()
    if env == "production":
        raise RuntimeError(
            "SECRET_KEY is not set. Refusing to start in production without one. "
            "Set SECRET_KEY in your environment (e.g. `python -c \"import secrets; "
            "print(secrets.token_urlsafe(48))\"` to generate one) before deploying."
        )

    ephemeral = secrets.token_urlsafe(48)
    app.config["SECRET_KEY"] = ephemeral
    logger.warning(
        "SECRET_KEY not set -- generated a random, process-local secret for this run only. "
        "Sessions/signed cookies will NOT survive a restart. This is fine for local "
        "development, but set a real SECRET_KEY in .env before deploying anywhere shared.",
    )
