from __future__ import annotations

import os

# These are public client credentials for the RπM Studio Supabase project.
# They are intentionally safe to ship in a desktop application. Never put a
# Supabase service_role / sb_secret key or database password in this file.
SUPABASE_URL = os.environ.get(
    "RPIM_SUPABASE_URL",
    "https://ajkeroxdsbpkkwmcbjjy.supabase.co",
).rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.environ.get(
    "RPIM_SUPABASE_PUBLISHABLE_KEY",
    "sb_publishable_gEV0eeyxE1N1lUIWvKUvOw_txsJAxGz",
).strip()

EULER_REGISTER_URL = "https://www.eulerstream.com/register"
EULER_QUICKSTART_URL = "https://www.eulerstream.com/docs/api/quickstart"
EULER_HOME_URL = "https://www.eulerstream.com/"
