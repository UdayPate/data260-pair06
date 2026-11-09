"""Company service (port 9063): company accounts and company profile."""
from app.routers import auth, companies
from services.common import create_service_app, routes_of

app = create_service_app(
    "company",
    "Company signup and company profile (including the logo).",
    routers=[routes_of(auth.router, "/auth/company/signup"), companies.router],
)   # company logos are uploaded here but served by the Student service (/media), from the shared MongoDB
