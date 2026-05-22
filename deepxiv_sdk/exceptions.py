"""
Exception types for deepxiv-sdk.

The exceptions are defined alongside the HTTP client in :mod:`deepxiv_sdk.reader`
and re-exported here (and from the package root) so they can be imported from a
stable, obvious location:

    from deepxiv_sdk import NotFoundError            # package root
    from deepxiv_sdk.exceptions import NotFoundError  # this module
"""
from .reader import (
    APIError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
    ServerError,
)

__all__ = [
    "APIError",
    "AuthenticationError",
    "BadRequestError",
    "NotFoundError",
    "RateLimitError",
    "ServerError",
]
