"""
FastAPI application entry point.

Run from the backend/ folder (port comes from the pair formula, 9000 + 6x10):
    uvicorn app.main:app --port 9060 --reload

Then open  http://localhost:9060/docs  for the interactive Swagger UI.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from . import mongo
from .config import FRONTEND_PORT, PAIR_STR
from .routers import applications, assistant, auth, companies, directory, events, jobs, media, meta, preferences, students

logger = logging.getLogger("handshake")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs when the app starts: create the unique rules and search indexes (safe to repeat; a database
    that is down does not stop the app from starting)."""
    mongo.ensure_indexes_quietly()
    yield


app = FastAPI(
    lifespan=lifespan,
    title=f"Handshake Clone API (Pair {PAIR_STR})",
    version="2.0.0",
    description=(
        "Student and Company platform for DATA-260 Labs 1 and 2 (all endpoints in one app; Lab 2 also runs them as six services).\n\n"
        "**How to authorize in Swagger:** call `POST /auth/login`, copy `access_token` "
        "from the response, click the **Authorize** button, and paste it."
    ),
)

# CORS (Cross-Origin Resource Sharing): browsers block a page on one address
# (the React app, port 9061) from calling an API on another (port 9060) unless the
# API explicitly allows it. This allows ONLY our own frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{FRONTEND_PORT}", f"http://127.0.0.1:{FRONTEND_PORT}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PyMongoError)
async def database_error_handler(request: Request, exc: PyMongoError):
    """Safety net: an unexpected database failure becomes a clean 500 JSON reply
    instead of a stack trace. The details go to the server log, not to the client."""
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "A database error occurred"})


app.include_router(auth.router)
app.include_router(students.router)
app.include_router(preferences.router)
app.include_router(directory.router)   # after students.router: that one owns /students/me
app.include_router(companies.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(events.router)
app.include_router(meta.router)
app.include_router(assistant.router)
app.include_router(media.router)       # public profile pictures (read from MongoDB GridFS)


@app.get("/health", tags=["Health"], summary="Is the API running?")
def health():
    return {"status": "ok", "pair": PAIR_STR}
