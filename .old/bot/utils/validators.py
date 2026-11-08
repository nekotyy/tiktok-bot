"""Validation utilities."""

from typing import Optional


def validate_file_size(file_size: int, max_size_bytes: int) -> tuple[bool, Optional[str]]:
    """Validate file size.

    Args:
        file_size: File size in bytes
        max_size_bytes: Maximum allowed size in bytes

    Returns:
        Tuple of (is_valid, error_message)
    """
    if file_size > max_size_bytes:
        max_mb = max_size_bytes / (1024 * 1024)
        actual_mb = file_size / (1024 * 1024)
        return False, f"Видео слишком большое ({actual_mb:.1f} МБ). Максимум: {max_mb:.0f} МБ"
    return True, None
