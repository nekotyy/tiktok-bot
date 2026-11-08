"""Initial schema."""

from alembic import op


revision = "20260427_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            video_url TEXT NOT NULL,
            file_size INTEGER,
            duration INTEGER,
            success BOOLEAN NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS statistics (
            user_id INTEGER PRIMARY KEY,
            total_downloads INTEGER DEFAULT 0,
            total_size INTEGER DEFAULT 0,
            last_download_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_downloads_user_id ON downloads(user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_downloads_created_at ON downloads(created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_statistics_user_id ON statistics(user_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_statistics_user_id")
    op.execute("DROP INDEX IF EXISTS idx_downloads_created_at")
    op.execute("DROP INDEX IF EXISTS idx_downloads_user_id")
    op.execute("DROP TABLE IF EXISTS statistics")
    op.execute("DROP TABLE IF EXISTS downloads")
    op.execute("DROP TABLE IF EXISTS users")
