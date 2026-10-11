"""Apply versioned migrations using the application's configured connection."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.database import sync_engine


def migrate():
    config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    with sync_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


if __name__ == "__main__":
    migrate()
