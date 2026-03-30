# Zahra LMS Backend - Project Summary

This document summarizes the development progress, technology stack, data models, and API endpoints of the Zahra LMS project. It can be used as a reference to port the project setup to another device.

## 1. Project Technology Stack
- **Framework:** Django 6.0.3 with Django Rest Framework (DRF) 3.16.1
- **Authentication:** Djoser paired with `djangorestframework_simplejwt` for secure JWT-based access
- **Database:** PostgreSQL (via `psycopg` 3.3.3)
- **Image Handling:** `django-resized` and `Pillow` (to convert/rescale images to WEBP, max 5MB)
- **API Documentation:** OpenAPI standard documented via `drf-spectacular` (Swagger & Redoc)
- **Environment Management:** Python virtual environment (`venv`) with `django-environ` for config loading
- **Other Utilities:** `django-filter` for query string filtering, `drf-nested-routers` for nested resource routing, `django-debug-toolbar` for debugging.

## 2. Implemented Apps & Data Models

### Accounts App (`accounts/`)
Handles custom user management and role-based profiles.
- **User:** Custom user model where `email` replaces `username` as the unique identifier. Also includes a `role` field (Admin, Teacher, Student).
- **TeacherProfile:** Extension of the `User` model. Includes `profile_picture` (WEBP converted), `professional_title`, `location`, `about`, `education`, `achievements` (JSON list), and `consultation_rate`.
- **StudentProfile:** Extension of the `User` model, currently holding a direct link to the user.

### Courses App (`courses/`)
Handles the core learning experience, lesson plans, enrollments, and scholarships.
- **CourseCategory & Course:** Defines a course containing details like `title`, `price`, `total_hours`, `thumbnail`, and `level` (beginner/intermediate/advanced). Linked to a `Category` and a `TeacherProfile`.
- **Enrollment:** Keeps track of which `User` is enrolled in which `Course`.
- **Curriculum:** Fully structured via `Module`, `Lesson`, `Quiz` (with `Question` & `Option`), and `Assignment`. Lessons track independent types (`video`, `document`, `quiz`, `assignment`, `external_link`) as well as a `duration_in_minutes` for time calculations.
- **Scholarship:** Enables users to submit an application form linked to a specific course, tracking their educational background and motivation.

### Consultations App (`consultations/`)
Facilitates booking one-on-one sessions with teachers.
- **Consultation:** Defines general details and base pricing linked to a `TeacherProfile`.
- **AvailableTimeslot:** Tracks available date, `start_time`, `end_time`, and whether the slot `is_booked` for an individual `Consultation`.
- **Bundle:** Allows an admin/teacher to create bulk-buy discounts (e.g. 5 sessions for 10% off).
- **ConsultationPurchase:** Records purchases made by students, tracking the applied bundle, the exact timeslots booked, and final paid amount.

## 3. Implemented API Endpoints & Routing

Through DRF routers and `drf-nested-routers`, the following RESTful patterns are live:

### Authentication (`/auth/`)
Provided by **Djoser** and **SimpleJWT**:
- `/auth/users/` (Registration, User Management)
- `/auth/jwt/create/` (Login / Get Token)
- `/auth/jwt/refresh/`, `/auth/jwt/verify/`

### Profile Profiles (`/`)
- `/teacher-profiles/`
- `/student-profiles/`

### Courses (`/`)
- `/courses/` -> Nested `/courses/{course_id}/modules/{module_id}/lessons/...`
- `/course-categories/`
- `/scholarships/`
- `/enrollments/`
- Deep nested curriculum:
  - `/courses/{course_id}/modules/{module_id}/lessons/{lesson_id}/quizzes/`
  - `/courses/{course_id}/modules/{module_id}/lessons/{lesson_id}/assignments/`

### Consultations (`/`)
- `/consultations/` -> Nested `/consultations/{id}/timeslots/` & `/consultations/{id}/bundles/`
- `/purchases/`

### API Documentation
- **Swagger UI:** `/docs/`
- **Redoc UI:** `/redoc/`
- **OpenAPI Schema:** `/schema/`

## 4. Porting to Another Device

To seamlessly port this project to another device, follow these steps:

1. **Clone/Copy:** Move the project directory (ignore the `venv/` folder and database dumps unless preserving data).
2. **Setup Venv:**
   ```bash
   python -m venv venv
   source venv/bin/activate
   # Or on Windows: venv\Scripts\activate
   ```
3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Environment Variables:**
   Copy the `.env.sample` file to `.env` and fill out your PostgreSQL database credentials, secret keys, debug flag, etc.
   ```bash
   cp .env.sample .env
   ```
5. **Database Setup:**
   Ensure PostgreSQL is running locally and matches your `.env` connection string. Create the database matching your setting.
6. **Migrate & Run:**
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py runserver
   ```
