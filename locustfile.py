"""
Locust load test for Zahra LMS API.

Usage:
    locust -f locustfile.py --host=http://localhost:8000

Then open http://localhost:8089 to start the test.

User types:
  - AnonymousUser  : browses public content (courses, blogs, videos, books, doors)
  - AuthenticatedUser : logs in then also hits authenticated endpoints (enrollments, profile)
"""

import random
from locust import HttpUser, task, between, events


# ---------------------------------------------------------------------------
# Seed data — update these to match what's in your DB
# ---------------------------------------------------------------------------
COURSE_SLUGS = [
    "python-for-data-science",
    "machine-learning-mastery",
    "django-rest-framework",
    "react-nextjs-complete-guide",
]

BLOG_SLUGS = [
    "getting-started-with-django",
    "understanding-ml-pipelines",
    "react-hooks-deep-dive",
    "postgresql-performance-tips",
]

BOOK_SLUGS = [
    "clean-code",
    "the-pragmatic-programmer",
    "django-for-professionals",
]

VIDEO_SLUGS = [
    "build-a-machine-learning-pipeline-in-30-minutes",
    "django-signals-explained",
    "10-vs-code-extensions-for-django-developers",
]

# Test credentials (created by `python manage.py seed`)
STUDENT_CREDENTIALS = {"email": "student1@example.com", "password": "student123"}


# ---------------------------------------------------------------------------
# Anonymous user — public browsing only
# ---------------------------------------------------------------------------
class AnonymousUser(HttpUser):
    weight = 3  # 3x more anonymous than authenticated
    wait_time = between(1, 4)

    @task(5)
    def course_list(self):
        self.client.get("/courses/", name="/courses/")

    @task(3)
    def course_detail(self):
        slug = random.choice(COURSE_SLUGS)
        self.client.get(f"/courses/{slug}/", name="/courses/<slug>/")

    @task(3)
    def blog_list(self):
        self.client.get("/blogs/", name="/blogs/")

    @task(2)
    def blog_detail(self):
        slug = random.choice(BLOG_SLUGS)
        self.client.get(f"/blogs/{slug}/", name="/blogs/<slug>/")

    @task(3)
    def video_list(self):
        self.client.get("/videos/", name="/videos/")

    @task(2)
    def video_detail(self):
        slug = random.choice(VIDEO_SLUGS)
        self.client.get(f"/videos/{slug}/", name="/videos/<slug>/")

    @task(2)
    def book_list(self):
        self.client.get("/books/", name="/books/")

    @task(1)
    def book_detail(self):
        slug = random.choice(BOOK_SLUGS)
        self.client.get(f"/books/{slug}/", name="/books/<slug>/")

    @task(2)
    def teacher_profiles(self):
        self.client.get("/teacher-profiles/", name="/teacher-profiles/")

    @task(1)
    def doors(self):
        self.client.get("/doors/", name="/doors/")

    @task(1)
    def consultations(self):
        self.client.get("/consultations/", name="/consultations/")


# ---------------------------------------------------------------------------
# Authenticated user — logs in on start, then hits protected endpoints
# ---------------------------------------------------------------------------
class AuthenticatedUser(HttpUser):
    weight = 1
    wait_time = between(2, 5)

    def on_start(self):
        """Log in and store the JWT token."""
        resp = self.client.post(
            "/auth/jwt/create/",
            json=STUDENT_CREDENTIALS,
            name="/auth/jwt/create/ [login]",
        )
        if resp.status_code == 200:
            token = resp.json().get("access")
            self.headers = {"Authorization": f"JWT {token}"}
        else:
            self.headers = {}

    @task(4)
    def course_list(self):
        self.client.get("/courses/", headers=self.headers, name="/courses/ [auth]")

    @task(3)
    def course_detail(self):
        slug = random.choice(COURSE_SLUGS)
        self.client.get(f"/courses/{slug}/", headers=self.headers, name="/courses/<slug>/ [auth]")

    @task(3)
    def my_enrollments(self):
        self.client.get("/enrollments/", headers=self.headers, name="/enrollments/")

    @task(2)
    def my_profile(self):
        self.client.get("/auth/users/me/", headers=self.headers, name="/auth/users/me/")

    @task(2)
    def blog_list(self):
        self.client.get("/blogs/", headers=self.headers, name="/blogs/ [auth]")

    @task(1)
    def video_list(self):
        self.client.get("/videos/", headers=self.headers, name="/videos/ [auth]")
