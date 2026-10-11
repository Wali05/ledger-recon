from alembic import context

from app.database import sync_engine
from app.models import Base

config = context.config


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError(
        "Run migrations against a connected database; legacy upgrades inspect existing tables"
    )
elif config.attributes.get("connection") is not None:
    run(config.attributes["connection"])
else:
    with sync_engine.begin() as connection:
        run(connection)
