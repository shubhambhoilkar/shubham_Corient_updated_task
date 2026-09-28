"""
Seeds the database with a sample crawl using the bundled fixture data, so an evaluator can
inspect a populated database (and hit the read endpoints) without running a live search first.

Usage:
    python scripts/seed_db.py
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")
_ENV_EXAMPLE_PATH = os.path.join(_PROJECT_ROOT, ".env.example")
if not os.path.exists(_ENV_PATH) and os.path.exists(_ENV_EXAMPLE_PATH):
    shutil.copy(_ENV_EXAMPLE_PATH, _ENV_PATH)
    print("[seed_db] No .env found -- created one from .env.example.", file=sys.stderr)

from dotenv import load_dotenv

load_dotenv(_ENV_PATH)

from app import create_app
from app.services import orchestrator
from app.settings_view import SettingsView


SEED_QUERIES = [
    ("iPhone 17 Pro", {"storage": "256GB", "colour": None, "budget_min": None, "budget_max": None}),
    ("iPhone 17", {"storage": "256GB", "colour": None, "budget_min": None, "budget_max": None}),
]


def main():
    app = create_app()
    with app.app_context():
        settings = SettingsView(app.config)
        for query, filters in SEED_QUERIES:
            result = orchestrator.run_search(settings, query, filters)
            print(
                f"Seeded '{query}': crawl #{result['crawl']['crawl_id']}, "
                f"{len(result['listings'])} listings across "
                f"{result['crawl']['sources_succeeded']} sources"
            )


if __name__ == "__main__":
    main()
