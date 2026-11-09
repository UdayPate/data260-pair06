"""Application service (port 9065): apply with a PDF resume, applicant lists, status changes, resumes."""
from app.routers import applications
from services.common import create_service_app

app = create_service_app(
    "application",
    "Apply to a job, list applications and applicants, change status, serve private resumes.",
    routers=[applications.router],
)
