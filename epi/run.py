import os
import shutil
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")
_ENV_EXAMPLE_PATH = os.path.join(_PROJECT_ROOT, ".env.example")

# Self-healing config: the documented quick-start is `cp .env.example .env`, but if that step
# is ever skipped (or the file goes missing from a checkout for any reason), regenerate .env
# from the committed example rather than letting the app fail to start over a missing file.
# This does NOT remove the need for .env.example to exist -- it removes the app's dependency
# on a manual copy step actually having been run.
if not os.path.exists(_ENV_PATH):
    if os.path.exists(_ENV_EXAMPLE_PATH):
        shutil.copy(_ENV_EXAMPLE_PATH, _ENV_PATH)
        print(
            "[startup] No .env found -- created one from .env.example with default/dev "
            "values. Edit .env before deploying anywhere real.",
            file=sys.stderr,
        )
    else:
        print(
            "[startup] Neither .env nor .env.example found. Falling back to hardcoded "
            "defaults in app/config.py (SQLite, fixture-mode scraping). This is fine for a "
            "quick look around, but set real config before deploying.",
            file=sys.stderr,
        )

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ENV_PATH)

from app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_ENV") == "development")
