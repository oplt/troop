from datetime import UTC, datetime


EMBEDDING_VECTOR_DIMENSIONS: int = 1536


def normalize_embedding_for_vector(values: list[float]) -> list[float]:
    dim = EMBEDDING_VECTOR_DIMENSIONS
    if not values:
        return [0.0] * dim
    if len(values) == dim:
        return values
    if len(values) > dim:
        return values[:dim]
    return values + [0.0] * (dim - len(values))


def utcnow() -> datetime:
    return datetime.now(UTC)
