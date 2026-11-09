"""Job service (port 9064): job postings, job search and the dropdown values (/meta)."""
from app.routers import jobs, meta
from services.common import create_service_app

app = create_service_app(
    "job",
    "Create, edit, search and view job postings. Also serves the dropdown options.",
    routers=[jobs.router, meta.router],
)
