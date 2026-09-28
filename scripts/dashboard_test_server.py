"""Ephemeral real API for dashboard integration tests; never uses atlas.db."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from apps.api.main import create_app

with tempfile.TemporaryDirectory(prefix='atlas-browser-tests-') as directory:
    uvicorn.run(create_app(f'sqlite:///{directory}/test.db', monitor=False), host='127.0.0.1', port=8011)
