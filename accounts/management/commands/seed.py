"""
Management command: python manage.py seed

Creates a full set of dummy data for local development/testing.
Safe to run on a clean database (after migrate). Idempotent — running
it twice will not duplicate top-level objects (users are looked-up by
email, singletons by pk=1).

Skips file/image fields — those are optional in all models.

Usage:
    python manage.py seed              # seed everything
    python manage.py seed --flush      # flush DB first, then seed
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, date, time
import random


class Command(BaseCommand):
    help = "Seed the database with dummy data for development/testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Flush the entire database before seeding.",
        )

    def handle(self, *args, **options):
        if options["flush"]:
            self.stdout.write(self.style.WARNING("Flushing database…"))
            from django.core.management import call_command
            call_command("flush", "--no-input")
            self.stdout.write(self.style.SUCCESS("Database flushed."))

        self._seed_all()

    # ------------------------------------------------------------------ #
    # Orchestrator                                                          #
    # ------------------------------------------------------------------ #

    def _seed_all(self):
        self._ok("─── Users & Profiles ───────────────────────────────")
        admin = self._seed_admin()
        teachers = self._seed_teachers()
        students = self._seed_students()

        self._ok("─── Site & Config ───────────────────────────────────")
        self._seed_site_settings()
        self._seed_membership_plan()
        self._seed_testimonials()
        self._seed_email_templates(admin)

        self._ok("─── Courses ─────────────────────────────────────────")
        course_cats = self._seed_course_categories()
        courses = self._seed_courses(teachers, course_cats)
        self._seed_modules_and_lessons(courses)
        self._seed_enrollments(students, courses)
        self._seed_scholarships(students, courses)
        self._seed_course_bundles(courses)

        self._ok("─── Consultations ───────────────────────────────────")
        consultations = self._seed_consultations(teachers)

        self._ok("─── Blogs ───────────────────────────────────────────")
        self._seed_blogs(teachers)

        self._ok("─── Books ───────────────────────────────────────────")
        self._seed_books()

        self._ok("─── Videos ──────────────────────────────────────────")
        self._seed_videos(teachers)

        self._ok("─── Reviews ─────────────────────────────────────────")
        self._seed_reviews(students, courses, consultations)

        self._ok("─── Doors ───────────────────────────────────────────")
        self._seed_doors()

        self._ok("─── Donations ───────────────────────────────────────")
        self._seed_donations()

        self._ok("─── Certificates ────────────────────────────────────")
        self._seed_certificates(admin, students, courses)

        self.stdout.write(self.style.SUCCESS("\n✅  Seed complete!"))
        self.stdout.write("")
        self.stdout.write("  Admin :  admin@example.com  /  admin123")
        for i, t in enumerate(teachers, 1):
            self.stdout.write(f"  Teacher {i}: {t.user.email}  /  teacher123")
        for i, s in enumerate(students, 1):
            self.stdout.write(f"  Student {i}: {s.user.email}  /  student123")
        self.stdout.write("")

    # ------------------------------------------------------------------ #
    # Users                                                                 #
    # ------------------------------------------------------------------ #

    def _seed_admin(self):
        from accounts.models import User
        user, created = User.objects.get_or_create(
            email="admin@example.com",
            defaults={
                "first_name": "Admin",
                "last_name": "User",
                "role": User.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        if created:
            user.set_password("admin123")
            user.save()
            self._ok(f"  Created admin: {user.email}")
        else:
            self._skip(f"  Admin already exists: {user.email}")
        return user

    def _seed_teachers(self):
        from accounts.models import User, TeacherProfile

        teachers_data = [
            {
                "email": "teacher1@example.com",
                "first_name": "Sarah",
                "last_name": "Mitchell",
                "professional_title": "Senior Data Scientist",
                "location": "New York, USA",
                "about": "10+ years experience in machine learning and data science. Passionate about making complex topics accessible.",
                "education": "Ph.D. Computer Science — MIT\nB.Sc. Mathematics — Harvard",
                "achievements": ["AWS Certified ML Specialist", "Published 12 research papers", "Kaggle Master"],
                "consultation_rate": "80.00",
                "offers_consultations": True,
            },
            {
                "email": "teacher2@example.com",
                "first_name": "James",
                "last_name": "Carter",
                "professional_title": "Full-Stack Engineer & Educator",
                "location": "London, UK",
                "about": "Building web applications for 8 years. Specialises in Django, React, and cloud-native architecture.",
                "education": "M.Sc. Software Engineering — Imperial College London",
                "achievements": ["Google Developer Expert", "Open-source contributor (10k+ stars)", "Ex-Meta engineer"],
                "consultation_rate": "60.00",
                "offers_consultations": True,
            },
        ]

        profiles = []
        for data in teachers_data:
            user, created = User.objects.get_or_create(
                email=data["email"],
                defaults={
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "role": User.TEACHER,
                    "is_active": True,
                },
            )
            if created:
                user.set_password("teacher123")
                user.save()
                self._ok(f"  Created teacher: {user.email}")
            else:
                self._skip(f"  Teacher already exists: {user.email}")

            profile = user.teacher_profile
            profile.professional_title = data["professional_title"]
            profile.location = data["location"]
            profile.about = data["about"]
            profile.education = data["education"]
            profile.achievements = data["achievements"]
            profile.consultation_rate = data["consultation_rate"]
            profile.offers_consultations = data["offers_consultations"]
            profile.save()
            profiles.append(profile)

        return profiles

    def _seed_students(self):
        from accounts.models import User

        students_data = [
            {"email": "student1@example.com", "first_name": "Alice", "last_name": "Johnson"},
            {"email": "student2@example.com", "first_name": "Bob", "last_name": "Williams"},
            {"email": "student3@example.com", "first_name": "Clara", "last_name": "Brown"},
        ]

        profiles = []
        for data in students_data:
            user, created = User.objects.get_or_create(
                email=data["email"],
                defaults={
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "role": User.STUDENT,
                    "is_active": True,
                },
            )
            if created:
                user.set_password("student123")
                user.save()
                self._ok(f"  Created student: {user.email}")
            else:
                self._skip(f"  Student already exists: {user.email}")
            profiles.append(user.student_profile)

        return profiles

    # ------------------------------------------------------------------ #
    # Site Settings & Config                                               #
    # ------------------------------------------------------------------ #

    def _seed_site_settings(self):
        from site_settings.models import SiteSettings
        settings, created = SiteSettings.objects.get_or_create(pk=1)
        settings.short_about = "Empowering learners worldwide with expert-led courses, consultations, and resources."
        settings.long_about = "<p>We are an online education platform dedicated to transforming lives through accessible, high-quality learning experiences.</p>"
        settings.privacy_policy = "<p>Your privacy is important to us. We collect only necessary data and never sell it to third parties.</p>"
        settings.terms_and_conditions = "<p>By using our platform, you agree to abide by our terms of service.</p>"
        settings.save()
        self._ok("  SiteSettings configured.")

    def _seed_membership_plan(self):
        from memberships.models import MembershipPlan
        plan, created = MembershipPlan.objects.get_or_create(
            pk=1,
            defaults={
                "name": "Premium Membership",
                "description": "Get unlimited access to all courses and exclusive content.",
                "price": "29.99",
                "duration_days": 30,
                "is_active": True,
            },
        )
        if not created:
            self._skip("  MembershipPlan already exists.")
        else:
            self._ok("  MembershipPlan created.")

    def _seed_testimonials(self):
        from site_settings.models import Testimonial
        if Testimonial.objects.exists():
            self._skip("  Testimonials already exist.")
            return

        testimonials = [
            {"name": "Maria Santos", "body": "This platform changed my career. The courses are incredibly practical and well-structured.", "order": 1},
            {"name": "Ahmed Al-Farsi", "body": "The consultations are worth every penny. My teacher gave me personalised guidance I couldn't find elsewhere.", "order": 2},
            {"name": "Priya Sharma", "body": "I went from zero to landing my first dev job in 6 months. The community and content here are world-class.", "order": 3},
            {"name": "Tom Fischer", "body": "Best investment I've made in my education. The books and video resources complement the courses perfectly.", "order": 4},
        ]
        for t in testimonials:
            Testimonial.objects.create(**t)
        self._ok(f"  Created {len(testimonials)} testimonials.")

    def _seed_email_templates(self, admin):
        from email_templates.models import EmailTemplateConfig, EmailPurpose
        if EmailTemplateConfig.objects.exists():
            self._skip("  EmailTemplateConfigs already exist.")
            return

        purposes = [
            (EmailPurpose.WELCOME, "d-welcome000000000000000000000001"),
            (EmailPurpose.PASSWORD_RESET, "d-passreset0000000000000000000001"),
            (EmailPurpose.COURSE_PURCHASE, "d-coursepurchase000000000000000001"),
            (EmailPurpose.CONSULTATION_PURCHASE, "d-consultpurchase00000000000000001"),
            (EmailPurpose.CERTIFICATE_ISSUED, "d-certissued000000000000000000001"),
            (EmailPurpose.MEMBERSHIP_PURCHASE, "d-membership000000000000000000001"),
        ]
        for purpose, template_id in purposes:
            EmailTemplateConfig.objects.create(
                purpose=purpose,
                sendgrid_template_id=template_id,
                is_active=True,
                updated_by=admin,
            )
        self._ok(f"  Created {len(purposes)} email template configs.")

    # ------------------------------------------------------------------ #
    # Courses                                                               #
    # ------------------------------------------------------------------ #

    def _seed_course_categories(self):
        from courses.models import CourseCategory
        categories_data = [
            {"name": "Data Science", "description": "Machine learning, statistics, and data analysis."},
            {"name": "Web Development", "description": "Frontend and backend web technologies."},
            {"name": "Business & Management", "description": "Leadership, strategy, and entrepreneurship."},
        ]
        categories = []
        for data in categories_data:
            cat, created = CourseCategory.objects.get_or_create(
                name=data["name"], defaults={"description": data["description"]}
            )
            categories.append(cat)
            if created:
                self._ok(f"  Created course category: {cat.name}")
            else:
                self._skip(f"  Course category already exists: {cat.name}")
        return categories

    def _seed_courses(self, teachers, categories):
        from courses.models import Course
        from config.utils import generate_unique_slug
        from django.utils.text import slugify
        courses_data = [
            {
                "title": "Python for Data Science",
                "subtitle": "From zero to hero in data analysis with Python",
                "description": "Learn Python, pandas, NumPy, Matplotlib, and Scikit-learn to solve real-world data problems.",
                "price": "149.00",
                "duration_in_weeks": 8,
                "hours_per_session": "1.5",
                "total_hours": "24.0",
                "level": "beginner",
                "status": "running",
                "start_date": date.today() - timedelta(days=14),
                "teacher": teachers[0],
                "category": categories[0],
            },
            {
                "title": "Machine Learning Mastery",
                "subtitle": "Deep dive into supervised and unsupervised learning",
                "description": "Covers regression, classification, clustering, neural networks, and model deployment.",
                "price": "199.00",
                "duration_in_weeks": 12,
                "hours_per_session": "2.0",
                "total_hours": "48.0",
                "level": "intermediate",
                "status": "upcoming",
                "start_date": date.today() + timedelta(days=30),
                "teacher": teachers[0],
                "category": categories[0],
            },
            {
                "title": "Django REST Framework",
                "subtitle": "Build production-grade APIs with Django",
                "description": "Learn DRF, authentication, permissions, serializers, viewsets, and deployment on AWS.",
                "price": "129.00",
                "duration_in_weeks": 6,
                "hours_per_session": "1.5",
                "total_hours": "18.0",
                "level": "intermediate",
                "status": "recorded",
                "teacher": teachers[1],
                "category": categories[1],
            },
            {
                "title": "React & Next.js Complete Guide",
                "subtitle": "Modern frontend development from scratch",
                "description": "Hooks, state management, server-side rendering, and deploying to Vercel.",
                "price": "119.00",
                "duration_in_weeks": 8,
                "hours_per_session": "1.5",
                "total_hours": "24.0",
                "level": "beginner",
                "status": "running",
                "start_date": date.today() - timedelta(days=7),
                "teacher": teachers[1],
                "category": categories[1],
            },
        ]

        courses = []
        for data in courses_data:
            slug = slugify(data["title"])
            course = Course.objects.filter(slug=slug).first()
            if course:
                self._skip(f"  Course already exists: {course.title}")
            else:
                data["slug"] = generate_unique_slug(Course, data["title"])
                course = Course.objects.create(**data)
                self._ok(f"  Created course: {course.title}")
            courses.append(course)
        return courses

    def _seed_modules_and_lessons(self, courses):
        from courses.models import Module, Lesson, Quiz, Question, Option, Assignment

        structure = {
            "Python for Data Science": [
                {
                    "title": "Getting Started with Python",
                    "lessons": [
                        {"title": "Welcome & Setup", "content_type": "video", "is_preview": True, "duration_in_minutes": 10},
                        {"title": "Python Basics", "content_type": "video", "duration_in_minutes": 45},
                        {"title": "Introduction Quiz", "content_type": "quiz", "duration_in_minutes": 15,
                         "quiz": {"time_limit": 15, "passing_score": 70, "questions": [
                             {"text": "What is a Python list?", "options": [
                                 ("An ordered mutable sequence", True),
                                 ("An ordered immutable sequence", False),
                                 ("A key-value store", False),
                             ]},
                             {"text": "Which keyword defines a function?", "options": [
                                 ("def", True), ("fun", False), ("function", False),
                             ]},
                         ]}},
                    ],
                },
                {
                    "title": "Data Analysis with Pandas",
                    "lessons": [
                        {"title": "DataFrames Explained", "content_type": "video", "duration_in_minutes": 50},
                        {"title": "Data Cleaning Techniques", "content_type": "document", "content": "https://example.com/pandas-cheatsheet.pdf", "duration_in_minutes": 30},
                        {"title": "Pandas Assignment", "content_type": "assignment", "duration_in_minutes": 60,
                         "assignment": {"description": "Analyse a real dataset", "instructions": "Download the CSV, clean it, and answer the 5 questions.", "due_date": timezone.now() + timedelta(days=7), "max_points": 100, "allowed_file_types": "ipynb, pdf", "max_file_size": 10}},
                    ],
                },
            ],
            "Django REST Framework": [
                {
                    "title": "DRF Fundamentals",
                    "lessons": [
                        {"title": "What is REST?", "content_type": "video", "is_preview": True, "duration_in_minutes": 12},
                        {"title": "Serializers Deep Dive", "content_type": "video", "duration_in_minutes": 55},
                        {"title": "REST Concepts Quiz", "content_type": "quiz", "duration_in_minutes": 20,
                         "quiz": {"time_limit": 20, "passing_score": 75, "questions": [
                             {"text": "Which HTTP method is idempotent?", "options": [
                                 ("PUT", True), ("POST", False), ("PATCH", False),
                             ]},
                         ]}},
                    ],
                },
                {
                    "title": "Authentication & Permissions",
                    "lessons": [
                        {"title": "JWT Authentication", "content_type": "video", "duration_in_minutes": 40},
                        {"title": "Custom Permissions", "content_type": "video", "duration_in_minutes": 35},
                        {"title": "Live Q&A Session", "content_type": "live", "duration_in_minutes": 60,
                         "scheduled_at": timezone.now() + timedelta(days=3)},
                    ],
                },
            ],
        }

        for course in courses:
            if course.title not in structure:
                continue
            if course.modules.exists():
                self._skip(f"  Modules already exist for: {course.title}")
                continue

            for module_order, module_data in enumerate(structure[course.title], 1):
                module = Module.objects.create(
                    course=course,
                    title=module_data["title"],
                    order=module_order,
                )
                for lesson_order, lesson_data in enumerate(module_data["lessons"], 1):
                    quiz_data = lesson_data.pop("quiz", None)
                    assignment_data = lesson_data.pop("assignment", None)

                    lesson = Lesson.objects.create(
                        module=module,
                        order=lesson_order,
                        **lesson_data,
                    )

                    if quiz_data:
                        questions = quiz_data.pop("questions", [])
                        quiz = Quiz.objects.create(lesson=lesson, **quiz_data)
                        for q_order, q_data in enumerate(questions, 1):
                            options = q_data.pop("options", [])
                            question = Question.objects.create(
                                quiz=quiz, text=q_data["text"], points=1
                            )
                            for opt_text, is_correct in options:
                                Option.objects.create(question=question, text=opt_text, is_correct=is_correct)

                    if assignment_data:
                        Assignment.objects.create(lesson=lesson, **assignment_data)

            self._ok(f"  Created modules/lessons for: {course.title}")

    def _seed_enrollments(self, students, courses):
        from courses.models import Enrollment
        # Enroll student1 in first 2 courses, student2 in course 3, student3 in all
        enroll_map = [
            (students[0].user, courses[:2]),
            (students[1].user, courses[2:3]),
            (students[2].user, courses),
        ]
        count = 0
        for user, user_courses in enroll_map:
            for course in user_courses:
                _, created = Enrollment.objects.get_or_create(user=user, course=course)
                if created:
                    count += 1
        self._ok(f"  Created {count} enrollments.")

    def _seed_scholarships(self, students, courses):
        from courses.models import Scholarship
        if Scholarship.objects.exists():
            self._skip("  Scholarships already exist.")
            return

        Scholarship.objects.create(
            user=students[2].user,
            course=courses[1],
            name="Clara Brown",
            email="student3@example.com",
            phone_number="+1-555-0103",
            address="789 Student Lane, Chicago, IL",
            current_level_of_study="undergrad",
            field_of_study="Computer Science",
            why_applying="I cannot afford the full price but am deeply motivated to learn ML.",
            how_will_it_help="It will help me build a career in data science and support my family.",
            agree_to_contact=True,
            status="pending",
        )
        self._ok("  Created 1 scholarship application.")

    def _seed_course_bundles(self, courses):
        from courses.models import Bundle
        if Bundle.objects.exists():
            self._skip("  Course bundles already exist.")
            return

        bundle = Bundle.objects.create(
            name="Data Science Complete Pack",
            description="Get both Python for Data Science and Machine Learning Mastery at a discount.",
            price="299.00",
            is_active=True,
        )
        bundle.courses.set(courses[:2])
        self._ok("  Created 1 course bundle.")

    # ------------------------------------------------------------------ #
    # Consultations                                                         #
    # ------------------------------------------------------------------ #

    def _seed_consultations(self, teachers):
        from consultations.models import Consultation, AvailableTimeslot, Bundle

        consultations_data = [
            {
                "teacher": teachers[0],
                "title": "Data Science Career Coaching",
                "description": "One-on-one guidance on breaking into data science, portfolio review, and interview prep.",
                "standard_price": "80.00",
            },
            {
                "teacher": teachers[1],
                "title": "Web Development Mentorship",
                "description": "Get unstuck on your Django or React project. Architecture advice and code reviews.",
                "standard_price": "60.00",
            },
        ]

        consultations = []
        for data in consultations_data:
            consultation, created = Consultation.objects.get_or_create(
                teacher=data["teacher"],
                title=data["title"],
                defaults={"description": data["description"], "standard_price": data["standard_price"]},
            )
            consultations.append(consultation)

            if created:
                self._ok(f"  Created consultation: {consultation.title}")

                # Add bundles
                Bundle.objects.create(
                    consultation=consultation,
                    num_sessions=3,
                    discount_percentage="10.00",
                )
                Bundle.objects.create(
                    consultation=consultation,
                    num_sessions=5,
                    discount_percentage="20.00",
                )

                # Add timeslots for next 7 days
                today = date.today()
                slots_created = 0
                for day_offset in range(1, 8):
                    slot_day = today + timedelta(days=day_offset)
                    if slot_day.weekday() < 5:  # Mon-Fri only
                        for start_hour in [10, 14, 16]:
                            AvailableTimeslot.objects.create(
                                consultation=consultation,
                                day=slot_day,
                                start_time=time(start_hour, 0),
                                end_time=time(start_hour + 1, 0),
                                is_booked=False,
                            )
                            slots_created += 1
                self._ok(f"    → {slots_created} timeslots, 2 bundles")
            else:
                self._skip(f"  Consultation already exists: {consultation.title}")

        return consultations

    # ------------------------------------------------------------------ #
    # Blogs                                                                 #
    # ------------------------------------------------------------------ #

    def _seed_blogs(self, teachers):
        from blogs.models import Blog, BlogCategory

        categories_data = ["Data Science", "Web Development", "Career Advice"]
        cats = {}
        for name in categories_data:
            cat, _ = BlogCategory.objects.get_or_create(name=name)
            cats[name] = cat

        blogs_data = [
            {
                "author": teachers[0],
                "category": cats["Data Science"],
                "title": "5 Python Libraries Every Data Scientist Needs in 2025",
                "excerpt": "From data wrangling to model deployment — here are the tools that belong in every data scientist's toolkit.",
                "content": "<p>Data science tooling has never been more mature. Here are the five libraries that will level up your workflow...</p><p>1. <strong>Polars</strong> — a blazing-fast DataFrame library...</p>",
                "status": "published",
            },
            {
                "author": teachers[0],
                "category": cats["Career Advice"],
                "title": "How I Got My First Data Science Job With No Experience",
                "excerpt": "A practical roadmap: building projects, networking, and cracking technical interviews.",
                "content": "<p>When I started, I had no formal CS background. Here's the honest path that worked for me...</p>",
                "status": "published",
            },
            {
                "author": teachers[1],
                "category": cats["Web Development"],
                "title": "Django vs FastAPI: Which Should You Choose in 2025?",
                "excerpt": "A detailed comparison of the two most popular Python backend frameworks.",
                "content": "<p>Both are excellent choices, but the right answer depends on your use case...</p>",
                "status": "published",
            },
            {
                "author": teachers[1],
                "category": cats["Web Development"],
                "title": "Deploying Django on AWS ECS: A Step-by-Step Guide",
                "excerpt": "From Docker image to production with load balancing, RDS, and CloudFront.",
                "content": "<p>This guide assumes you have a working Django app and basic AWS knowledge...</p>",
                "status": "draft",
            },
        ]

        count = 0
        for data in blogs_data:
            from config.utils import generate_unique_slug
            from django.utils.text import slugify as _slugify
            slug = _slugify(data["title"])
            if Blog.objects.filter(slug=slug).exists():
                self._skip(f"  Blog already exists: {data['title']}")
                continue
            data["slug"] = generate_unique_slug(Blog, data["title"])
            Blog.objects.create(**data)
            count += 1

        self._ok(f"  Created {count} blogs.")

    # ------------------------------------------------------------------ #
    # Books                                                                 #
    # ------------------------------------------------------------------ #

    def _seed_books(self):
        from books.models import Book, BookCategory

        cats_data = ["Computer Science", "Business", "Self-Development"]
        cats = {}
        for name in cats_data:
            cat, _ = BookCategory.objects.get_or_create(name=name)
            cats[name] = cat

        books_data = [
            {
                "category": cats["Computer Science"],
                "title": "Clean Code in Python",
                "author": "Sarah Mitchell",
                "author_designation": "Senior Data Scientist",
                "description": "Learn to write readable, maintainable Python code that your teammates will love.",
                "isbn": "9780135957059",
                "language": "English",
                "publisher": "TechPress",
                "published_date": date(2023, 3, 15),
                "number_of_pages": 312,
                "has_digital": True,
                "digital_price": "19.99",
                "has_physical": True,
                "physical_price": "34.99",
                "stock_count": 50,
                "tags": ["python", "clean code", "best practices"],
            },
            {
                "category": cats["Computer Science"],
                "title": "Full-Stack Django: A Practical Guide",
                "author": "James Carter",
                "author_designation": "Full-Stack Engineer & Educator",
                "description": "Build complete web applications with Django, React, and PostgreSQL.",
                "isbn": "9781492051442",
                "language": "English",
                "publisher": "O'Reilly Media",
                "published_date": date(2024, 1, 10),
                "number_of_pages": 420,
                "has_digital": True,
                "digital_price": "24.99",
                "has_physical": False,
                "physical_price": "0.00",
                "stock_count": 0,
                "tags": ["django", "react", "full-stack"],
            },
            {
                "category": cats["Self-Development"],
                "title": "The Learner's Mindset",
                "author": "Dr. Amara Osei",
                "author_designation": "Educational Psychologist",
                "description": "Science-backed strategies to learn faster, retain more, and build lasting skills.",
                "isbn": "9780062316110",
                "language": "English",
                "publisher": "HarperCollins",
                "published_date": date(2022, 9, 5),
                "number_of_pages": 256,
                "has_digital": True,
                "digital_price": "14.99",
                "has_physical": True,
                "physical_price": "22.99",
                "stock_count": 80,
                "tags": ["learning", "mindset", "education"],
            },
        ]

        count = 0
        for data in books_data:
            _, created = Book.objects.get_or_create(
                isbn=data["isbn"],
                defaults=data,
            )
            if created:
                from config.utils import generate_unique_slug
                # slug is auto-generated in Book.save() via slugify
                count += 1

        self._ok(f"  Created {count} books.")

    # ------------------------------------------------------------------ #
    # Videos                                                               #
    # ------------------------------------------------------------------ #

    def _seed_videos(self, teachers):
        from videos.models import Video, VideoCategory

        cats_data = ["Tutorials", "Webinars", "Tips & Tricks"]
        cats = {}
        for name in cats_data:
            cat, _ = VideoCategory.objects.get_or_create(name=name)
            cats[name] = cat

        videos_data = [
            {
                "author": teachers[0],
                "category": cats["Tutorials"],
                "title": "Build a Machine Learning Pipeline in 30 Minutes",
                "excerpt": "End-to-end ML: data ingestion, preprocessing, training, and evaluation.",
                "content": "In this video we build a complete ML pipeline using scikit-learn and pandas.",
                "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "status": "published",
            },
            {
                "author": teachers[1],
                "category": cats["Tutorials"],
                "title": "Django Signals Explained",
                "excerpt": "When and how to use Django's signal framework without creating a mess.",
                "content": "Signals are powerful but often misused. This video shows best practices.",
                "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "status": "published",
            },
            {
                "author": teachers[1],
                "category": cats["Tips & Tricks"],
                "title": "10 VS Code Extensions for Django Developers",
                "excerpt": "Supercharge your productivity with these must-have extensions.",
                "content": "From linting to database management, these extensions will save you hours.",
                "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "status": "draft",
            },
        ]

        count = 0
        for data in videos_data:
            from config.utils import generate_unique_slug
            from django.utils.text import slugify as _slugify
            slug = _slugify(data["title"])
            if Video.objects.filter(slug=slug).exists():
                self._skip(f"  Video already exists: {data['title']}")
                continue
            data["slug"] = generate_unique_slug(Video, data["title"])
            Video.objects.create(**data)
            count += 1

        self._ok(f"  Created {count} videos.")

    # ------------------------------------------------------------------ #
    # Reviews                                                              #
    # ------------------------------------------------------------------ #

    def _seed_reviews(self, students, courses, consultations):
        from reviews.models import Review
        if Review.objects.exists():
            self._skip("  Reviews already exist.")
            return

        reviews_data = [
            {"user": students[0].user, "review_type": "course", "course": courses[0], "rating": 5, "comment": "Absolutely brilliant course. The projects were challenging but rewarding."},
            {"user": students[2].user, "review_type": "course", "course": courses[0], "rating": 4, "comment": "Great content. Would love more exercises."},
            {"user": students[1].user, "review_type": "course", "course": courses[2], "rating": 5, "comment": "Best DRF course I've found. Clear explanations and real-world examples."},
            {"user": students[0].user, "review_type": "consultation", "consultation": consultations[0], "rating": 5, "comment": "Sarah gave me incredibly actionable advice. Got a job offer 3 weeks later!"},
        ]

        for data in reviews_data:
            Review.objects.create(**data)

        self._ok(f"  Created {len(reviews_data)} reviews.")

    # ------------------------------------------------------------------ #
    # Doors                                                                 #
    # ------------------------------------------------------------------ #

    def _seed_doors(self):
        from doors.models import Door
        if Door.objects.exists():
            self._skip("  Doors already exist.")
            return

        doors = [
            {"title": "Courses", "content": "Browse our expert-led courses and start learning today.", "redirect_link": "/courses", "is_visible": True},
            {"title": "Consultations", "content": "Book a one-on-one session with our teachers.", "redirect_link": "/consultations", "is_visible": True},
            {"title": "Books", "content": "Explore our curated library of educational books.", "redirect_link": "/books", "is_visible": True},
            {"title": "Blog", "content": "Read expert articles and stay up to date.", "redirect_link": "/blog", "is_visible": True},
        ]
        for data in doors:
            Door.objects.create(**data)
        self._ok(f"  Created {len(doors)} doors.")

    # ------------------------------------------------------------------ #
    # Donations                                                            #
    # ------------------------------------------------------------------ #

    def _seed_donations(self):
        from donations.models import Donation
        if Donation.objects.exists():
            self._skip("  Donations already exist.")
            return

        donations = [
            {"first_name": "John", "last_name": "Doe", "email": "john@example.com", "amount": "50.00", "status": "completed", "stripe_reference": "pi_test_donation_001"},
            {"first_name": "Lisa", "last_name": "Park", "email": "lisa@example.com", "amount": "100.00", "status": "completed", "stripe_reference": "pi_test_donation_002"},
            {"first_name": "Michael", "last_name": "Chen", "email": "michael@example.com", "amount": "25.00", "status": "pending"},
        ]
        for data in donations:
            Donation.objects.create(**data)
        self._ok(f"  Created {len(donations)} donations.")

    # ------------------------------------------------------------------ #
    # Certificates                                                         #
    # ------------------------------------------------------------------ #

    def _seed_certificates(self, admin, students, courses):
        from certificates.models import CertificateTemplate, Certificate
        from courses.models import Enrollment

        template, created = CertificateTemplate.objects.get_or_create(
            name="Standard Certificate",
            defaults={"created_by": admin},
        )
        if created:
            self._ok("  Created certificate template.")

        # Issue a certificate for student1's first enrolled course if they have it
        try:
            enrollment = Enrollment.objects.get(user=students[0].user, course=courses[0])
            _, created = Certificate.objects.get_or_create(
                student=students[0].user,
                course=courses[0],
                defaults={
                    "enrollment": enrollment,
                    "template": template,
                    "issued_by": admin,
                },
            )
            if created:
                self._ok("  Issued 1 certificate to Alice for Python for Data Science.")
            else:
                self._skip("  Certificate already exists.")
        except Enrollment.DoesNotExist:
            self._skip("  Skipping certificate — enrollment not found.")

    # ------------------------------------------------------------------ #
    # Helpers                                                               #
    # ------------------------------------------------------------------ #

    def _ok(self, msg):
        self.stdout.write(self.style.SUCCESS(msg))

    def _skip(self, msg):
        self.stdout.write(self.style.WARNING(msg))
