"""
Utility functions for file handling and text processing
"""

import re
from pathlib import Path


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """
    Sanitize filename by removing illegal characters

    Args:
        filename: Original filename
        max_length: Maximum length of filename

    Returns:
        Sanitized filename
    """
    # Remove illegal characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)

    # Replace special characters
    filename = filename.replace('\n', ' ').replace('\r', ' ')

    # Remove multiple spaces
    filename = re.sub(r'\s+', ' ', filename).strip()

    # Limit length
    if len(filename) > max_length:
        filename = filename[:max_length]

    return filename


def ensure_dir(path: Path) -> Path:
    """
    Ensure directory exists, create if not

    Args:
        path: Directory path

    Returns:
        The path
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_title(title: str) -> str:
    """
    Normalize title for comparison (remove punctuation, lowercase)

    Args:
        title: Original title

    Returns:
        Normalized title
    """
    import string
    title = title.lower()
    title = title.translate(str.maketrans('', '', string.punctuation))
    title = ' '.join(title.split())
    return title


def titles_match(title1: str, title2: str) -> bool:
    """
    Check if two titles match (ignoring case and punctuation)

    Args:
        title1: First title
        title2: Second title

    Returns:
        True if titles match
    """
    return normalize_title(title1) == normalize_title(title2)
