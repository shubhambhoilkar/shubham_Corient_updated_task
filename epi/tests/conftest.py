import os
import tempfile

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db as _db


@pytest.fixture()
def app():
    # A real (temp) file-based SQLite DB, not `:memory:`. `:memory:` gives every new
    # connection its own separate, empty database unless connection-sharing tricks are used,
    # and those tricks (a single shared connection across threads) turn out to be actively
    # unsafe under genuine concurrent writes -- they don't provide real isolation, they just
    # let multiple threads corrupt the same connection's transaction state instead of raising
    # a clear error. A temp file lets SQLite's own (real, working) file-locking do this
    # properly, which is what a real single-node deployment would rely on too. Each test gets
    # its own fresh temp file so tests can't see each other's data.
    db_fd, db_path = tempfile.mkstemp(suffix=".db")

    class _PerTestConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
        # Generous busy-timeout: under concurrent writes SQLite can raise "database is
        # locked" if a writer doesn't hear back within the default ~5s; our concurrency
        # tests are small and fast, but a slow CI runner shouldn't turn that into a flaky
        # test failure that has nothing to do with the actual behaviour being tested.
        SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 30}}

    application = create_app(_PerTestConfig)
    with application.app_context():
        yield application

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    yield _db
    _db.session.remove()
    for table in reversed(_db.metadata.sorted_tables):
        _db.session.execute(table.delete())
    _db.session.commit()
