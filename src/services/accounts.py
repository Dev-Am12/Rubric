"""
services.accounts: domain service entrypoint for user accounts and authentication.
Re-exports from accounts.services.
"""

from accounts.services import (
    register,
    login,
    logout,
    GENERIC_LOGIN_ERROR,
)

__all__ = [
    "register",
    "login",
    "logout",
    "GENERIC_LOGIN_ERROR",
]
