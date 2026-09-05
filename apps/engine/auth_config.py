from __future__ import annotations

import os

# Local Supabase CLI defaults for development; override via env in production builds.
_DEFAULT_SUPABASE_URL = "http://127.0.0.1:54321"
_DEFAULT_SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9."
    "CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0"
)
_DEFAULT_AUTH_URL = "http://127.0.0.1:5173"

SUPABASE_URL = (os.environ.get("SUPABASE_URL") or _DEFAULT_SUPABASE_URL).rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY") or _DEFAULT_SUPABASE_ANON_KEY
CA_UNPACKER_AUTH_URL = (
    os.environ.get("CA_UNPACKER_AUTH_URL") or _DEFAULT_AUTH_URL
).rstrip("/")
