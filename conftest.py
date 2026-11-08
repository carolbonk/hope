"""Run every test on its own tenant and agency, so pytest never wipes the `make demo` data.

DB tests share the local Postgres with `make demo`, and the hackathon fixtures clear the
configured tenant's users, jobs and profile. Env vars beat `.env`, so these IDs win.
"""

from __future__ import annotations

import os

os.environ["HOPE_TENANT_ID"] = "00000000-0000-4000-8000-00000000e570"
os.environ["HOPE_AGENCY_ID"] = "00000000-0000-4000-8000-0000000ae570"
