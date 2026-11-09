"""Student service (port 9062): student accounts, sign-in, profile, preferences, student directory."""
from app.routers import auth, directory, preferences, students
from services.common import create_service_app, routes_of

app = create_service_app(
    "student",
    "Student signup, login/logout/me (for both roles), profile, preferences, activity heatmap, student directory.",
    routers=[
        routes_of(auth.router, "/auth/student/signup", "/auth/login", "/auth/logout", "/auth/me"),
        students.router,
        preferences.router,
        directory.router,          # after students.router: that one owns /students/me
    ],
    serve_profile_pictures=True,
)
