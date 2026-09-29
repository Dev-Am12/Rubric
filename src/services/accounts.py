"""
services.accounts: domain service entrypoint for user accounts and authentication.
Re-exports from accounts.services.
"""

from accounts.services import (
    register,
    login,
    logout,
    GENERIC_LOGIN_ERROR,
    check_auth_rate_limit,
    hash_ip,
    get_client_ip,
    AUTH_RATE_LIMIT_ATTEMPTS,
    AUTH_RATE_LIMIT_WINDOW,
    AUTH_RATE_LIMIT_MESSAGE,
)

__all__ = [
    "register",
    "login",
    "logout",
    "GENERIC_LOGIN_ERROR",
    "check_auth_rate_limit",
    "hash_ip",
    "get_client_ip",
    "AUTH_RATE_LIMIT_ATTEMPTS",
    "AUTH_RATE_LIMIT_WINDOW",
    "AUTH_RATE_LIMIT_MESSAGE",
]
