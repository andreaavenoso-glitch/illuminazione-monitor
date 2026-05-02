"""slowapi-based rate limiter, keyed by client IP.

Used on /auth/login (10/min) and any other write endpoint that should
be brute-force resistant.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
