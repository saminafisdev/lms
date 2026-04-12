"""
Locust load test for Zahra LMS API.

Usage:
    locust -f locustfile.py --host=http://localhost:8000

Then open http://localhost:8089 to start the test.

Slugs and IDs are fetched from the API automatically before the test starts.
"""

import random
import requests
from locust import HttpUser, task, between, events

# Populated automatically at test start via fetch_seed_data()
COURSE_SLUGS = []
BLOG_SLUGS = []
BOOK_SLUGS = []
VIDEO_SLUGS = []

STUDENT_CREDENTIALS = {"email": "student1@example.com", "password": "student123"}

HOST = "http://localhost:8000"


def fetch_slugs(url, key="slug"):
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        results = data.get("results", data) if isinstance(data, dict) else data
        return [item[key] for item in results if key in item]
    except Exception as e:
        print(f"[locust] Warning: could not fetch {url} — {e}")
        return []


@events.test_start.add_listener
def fetch_seed_data(environment, **kwargs):
    base = environment.host or HOST
    print(f"[locust] Fetching seed data from {base}...")

    COURSE_SLUGS.extend(fetch_slugs(f"{base}/courses/?page_size=100"))
    BLOG_SLUGS.extend(fetch_slugs(f"{base}/blogs/?page_size=100"))
    BOOK_SLUGS.extend(fetch_slugs(f"{base}/books/?page_size=100"))
    VIDEO_SLUGS.extend(fetch_slugs(f"{base}/videos/?page_size=100"))

    print(f"[locust] Loaded: {len(COURSE_SLUGS)} courses, {len(BLOG_SLUGS)} blogs, "
          f"{len(BOOK_SLUGS)} books, {len(VIDEO_SLUGS)} videos")


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
        if not COURSE_SLUGS:
            return
        slug = random.choice(COURSE_SLUGS)
        self.client.get(f"/courses/{slug}/", name="/courses/<slug>/")

    @task(3)
    def blog_list(self):
        self.client.get("/blogs/", name="/blogs/")

    @task(2)
    def blog_detail(self):
        if not BLOG_SLUGS:
            return
        slug = random.choice(BLOG_SLUGS)
        self.client.get(f"/blogs/{slug}/", name="/blogs/<slug>/")

    @task(3)
    def video_list(self):
        self.client.get("/videos/", name="/videos/")

    @task(2)
    def video_detail(self):
        if not VIDEO_SLUGS:
            return
        slug = random.choice(VIDEO_SLUGS)
        self.client.get(f"/videos/{slug}/", name="/videos/<slug>/")

    @task(2)
    def book_list(self):
        self.client.get("/books/", name="/books/")

    @task(1)
    def book_detail(self):
        if not BOOK_SLUGS:
            return
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
