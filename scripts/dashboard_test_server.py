"""Ephemeral real API for dashboard integration tests; never uses atlas.db."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from apps.api.main import create_app
from apps.api.migrations import upgrade_database

with tempfile.TemporaryDirectory(prefix='atlas-browser-tests-') as directory:
    database_url = f'sqlite:///{directory}/test.db'
    upgrade_database(database_url)
    uvicorn.run(
        create_app(
            database_url,
            monitor=False,
            bootstrap_admin_password='atlas-browser-admin-password',
        ),
        host='127.0.0.1',
        port=8011,
    )
