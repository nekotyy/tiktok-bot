"""Add chat_settings table."""

from alembic import op


revision = "20260512_0002"
down_revision = "20260427_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_settings (
            chat_id INTEGER PRIMARY KEY,
            require_pure_link BOOLEAN NOT NULL DEFAULT 0,
            delete_source_messages BOOLEAN NOT NULL DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_settings_chat_id ON chat_settings(chat_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chat_settings_chat_id")
    op.execute("DROP TABLE IF EXISTS chat_settings")
