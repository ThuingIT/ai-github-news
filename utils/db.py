"""
utils/db.py — Shared Supabase client factory.
Import get_client() instead of instantiating supabase directly.
"""
import os
from supabase import create_client, Client

_client: Client | None = None


def get_client() -> Client:
    """Return a cached Supabase client, creating it on first call."""
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise EnvironmentError("SUPABASE_URL and SUPABASE_KEY must be set.")
        _client = create_client(url, key)
    return _client
