"""
Pair-derived configuration for DATA-260 Labs 1 and 2 (Pair 06).

Every value below is derived from PAIR exactly as the handout requires:
    PORT_BASE = 9000 + (PAIR x 10)
    DB / Kafka prefix = p{PAIR}
    SEED = PAIR (used for every generator and random_state)
Secrets (database connection string, JWT secret) come from environment variables or a .env file that is NOT committed.
"""
import os
from datetime import date

from dotenv import load_dotenv

load_dotenv()  # reads backend/.env if it exists

# ---- Pair parameters (report these in README and report) ----
PAIR = 6
PAIR_STR = f"{PAIR:02d}"          # "06"
PORT_BASE = 9000 + PAIR * 10      # 9060
BACKEND_PORT = PORT_BASE          # 9060 -> FastAPI
FRONTEND_PORT = PORT_BASE + 1     # 9061 -> React dev server

# Lab 2: the backend is split into six services. Each gets its own port, counted up from
# the frontend port (9060 is the gateway that routes to them, 9061 is the website).
SERVICE_PORTS = {
    "student": PORT_BASE + 2,      # 9062
    "company": PORT_BASE + 3,      # 9063
    "job": PORT_BASE + 4,          # 9064
    "application": PORT_BASE + 5,  # 9065
    "event": PORT_BASE + 6,        # 9066
    "assistant": PORT_BASE + 7,    # 9067
}
DB_PREFIX = f"p{PAIR_STR}"        # "p06"
SEED = PAIR                       # 6
CITY_SET = ["San Jose", "Sunnyvale", "Mountain View"]
STATE = "CA"

# Fixed "today" for the seed data so the generated dates are reproducible.
# Events are spread around this date so most are upcoming during grading.
ANCHOR_DATE = date(2026, 10, 5)

# ---- Database (Lab 2: MongoDB; Lab 1 used MySQL) ----
DB_NAME = f"{DB_PREFIX}_handshake"  # p06_handshake
# One connection string for every service. In Docker/Kubernetes it comes from an environment variable or a
# Secret (it may contain a password), never from a committed file.
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", DB_NAME)
MONGO_TIMEOUT_MS = int(os.getenv("MONGO_TIMEOUT_MS", "5000"))   # how long to wait for a MongoDB that does not answer

# ---- Auth ----
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 8        # also the lifetime of the session document in MongoDB (it expires by itself)
