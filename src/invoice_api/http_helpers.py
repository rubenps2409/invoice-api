from fastapi import HTTPException


def retry_later(status_code: int, detail: str, retry_after_seconds: int) -> HTTPException:
    """An error that tells the client when to try again (Retry-After, in seconds)."""
    return HTTPException(
        status_code, detail, headers={"Retry-After": str(retry_after_seconds)}
    )
