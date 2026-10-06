"""
FastAPI application entry point.

Run from the backend/ folder (port comes from the pair formula, 9000 + 6x10):
    uvicorn app.main:app --port 9060 --reload

Then open  http://localhost:9060/docs  for the interactive Swagger UI.
"""
import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from .config import FRONTEND_PORT, PAIR_STR, UPLOAD_DIR
from .routers import auth, companies, meta, students

logger = logging.getLogger("handshake")

app = FastAPI(
    title=f"Handshake Clone API (Pair {PAIR_STR})",
    version="1.0.0",
    description=(
        "Student and Company platform for DATA-260 Lab 1.\n\n"
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

# Folders for uploads (git ignores them, so create them if missing).
PROFILE_PICS_DIR = os.path.join(UPLOAD_DIR, "profile_pics")
os.makedirs(PROFILE_PICS_DIR, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, "resumes"), exist_ok=True)

# Profile pictures are public (like on LinkedIn), so we serve ONLY that sub-folder.
# Resumes are private: the uploads/resumes folder is deliberately NOT mounted here.
# They will be sent through a login-protected endpoint that checks who is asking.
app.mount("/media/profile_pics", StaticFiles(directory=PROFILE_PICS_DIR), name="profile_pics")


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    """Safety net: an unexpected database failure becomes a clean 500 JSON reply
    instead of a stack trace. The details go to the server log, not to the client."""
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "A database error occurred"})


app.include_router(auth.router)
app.include_router(students.router)
app.include_router(companies.router)
app.include_router(meta.router)


@app.get("/health", tags=["Health"], summary="Is the API running?")
def health():
    return {"status": "ok", "pair": PAIR_STR}