# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit, repeatable v1 migration for existing SQLite and PostgreSQL databases."""

from sqlalchemy import inspect, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..store.models import Base
from .models import DialogueBase, SchemaVersion


def migrate(engine) -> None:
    # New tables only: no legacy event import and no guessed ownership backfill.
    # Run during deployment before workers, rather than relying on app create_all.
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        for table in DialogueBase.metadata.sorted_tables:
            table.create(connection, checkfirst=True)
            existing = {c["name"] for c in inspect(connection).get_columns(table.name)}
            if not {c.name for c in table.columns}.issubset(existing):
                raise RuntimeError("incompatible dialogue schema; explicit upgrade required")
        factory = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
        connection.execute(
            factory(SchemaVersion)
            .values(name="dialogue", version=1)
            .on_conflict_do_nothing(index_elements=[SchemaVersion.name])
        )
        if connection.execute(select(SchemaVersion.version)).scalar() != 1:
            raise RuntimeError("unsupported dialogue schema version")


if __name__ == "__main__":
    from ..store.db import engine

    migrate(engine)
    print("dialogue migration v1 complete")
