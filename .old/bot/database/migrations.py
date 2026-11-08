"""Alembic migration helpers."""

from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig

from bot.config import Config


def upgrade_database() -> None:
    """Apply all Alembic migrations up to head."""
    project_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = project_root / "alembic.ini"
    alembic_dir = project_root / "alembic"

    alembic_cfg = AlembicConfig(str(alembic_ini_path))
    alembic_cfg.set_main_option("script_location", str(alembic_dir))
    alembic_cfg.set_main_option("sqlalchemy.url", Config.get_database_url())

    command.upgrade(alembic_cfg, "head")
