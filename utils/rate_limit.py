"""
Rate Limiting Configuration
============================
Centralised rate-limit settings used across API routers.
All limits are per IP address (or per user when token is present).

Limits are intentionally generous for rural / low-bandwidth users
who may have high latency and need to retry more often.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# One shared Limiter instance imported by all routers
limiter = Limiter(key_func=get_remote_address, default_limits=["200/day", "50/hour"])

# Per-route overrides (used as decorator arguments):
#   @limiter.limit("5/minute")    → auth endpoints
#   @limiter.limit("20/minute")   → chat / ask
#   @limiter.limit("10/minute")   → quiz generate
#   @limiter.limit("30/minute")   → search
#   @limiter.limit("5/minute")    → admin upload
