"""Run identical workflow tests on SQLite and, when configured, PostgreSQL.

ATLAS_TEST_POSTGRES_URL must point to a test database whose user may create
schemas. Each test gets an isolated generated schema; existing schemas are
never dropped.
"""
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from apps.api.main import create_app


POSTGRES_URL = os.getenv('ATLAS_TEST_POSTGRES_URL')


@pytest.fixture(params=['sqlite', 'postgres'] if POSTGRES_URL else ['sqlite'])
def database_url(request, tmp_path):
    if request.param == 'sqlite':
        yield f'sqlite:///{tmp_path}/test.db'
        return
    schema = f'atlas_test_{uuid4().hex}'
    admin = create_engine(POSTGRES_URL)
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    try:
        yield make_url(POSTGRES_URL).update_query_dict({'options': f'-csearch_path={schema}'})
    finally:
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


@pytest.fixture
def system(database_url):
    clock = [datetime(2026, 10, 1, tzinfo=timezone.utc)]
    app = create_app(database_url, clock=lambda: clock[0], monitor=False)
    with TestClient(app) as client:
        yield client, clock, app
