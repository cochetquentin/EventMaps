import hashlib


def make_event_id(parts: list[str]) -> str:
    """Generate a stable 16-character hex event ID from a list of discriminating parts.

    Algorithm: sha256("|".join(parts))[:16]

    IMPORTANT: never change this algorithm — persisted IDs depend on it.
    """
    key = "|".join(parts)
    return hashlib.sha256(key.encode()).hexdigest()[:16]
