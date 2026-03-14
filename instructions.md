# Zahra LMS Project Overview

## Project Stack
- **Backend Framework**: Django with Django Rest Framework (DRF)
- **Authentication**: Djoser and Django Rest Framework SimpleJWT
- **Database**: PostgreSQL
- **Packages**: Continuously scan `requirements.txt` to check the packages before installing. Also after installing, pip freeze to the txt file.
- **Virtual Environment Path**: `/home/samin/projects/zahra/venv`
- **Image Handling**: django-resized (max upload size: 5MB, format to webp)

---

## Project Description
This project is an LMS (Learning Management System) that allows for the management of **Students**, **Teachers**, and **Courses**. It includes features for handling **users**, **courses**, **consultations**, and **scholarships**. The client already has a Tutor LMS website and is now looking to build a custom version using **Django**, **DRF**, and **PostgreSQL**.

---

## Users
There are three types of users in the system: **Admin**, **Teacher**, and **Student**. 

### 1. Admin
- **Admin Role**: Can manage all users and courses.

### 2. Teacher
A teacher can be linked to a Django User and will have the following additional fields:
- **Profile Picture**: Upload a profile picture (use `django-resized` for resizing, max size: 5MB, format: webp).
- **Professional Title**: The teacher's professional title.
- **Location**: The teacher’s location (city/country).
- **About**: A short bio about the teacher.
- **Education**: List of degrees and institutions where the teacher studied.
- **Achievements and Credentials**: Multiple text fields where each teacher can add achievements and credentials.
- **Consultation Rate**: The rate for teaching courses and/or consultations.
  
**Note**: A teacher can take courses or one-on-one consultations or both.

### 3. Student
A student is also linked to a Django User with standard fields like first name, last name, email, and password. No username required.

---

## Features

### 1. User Management
- **Admin**: Can create users separately for students and teachers. The admin can assign roles to the users (Admin, Teacher, Student).

---

### 2. Courses
Courses have the following fields:
- **Category**: The category of the course.
- **Title**: Name of the course.
- **Subtitle**: Short description or tagline of the course.
- **Description**: Rich text field for a detailed course description.
- **Price**: The price of the course in USD.
- **Duration**: Number of weeks for the course.
- **Hours per Session**: Number of hours per session.
- **Level**: Course difficulty (values: `beginner`, `intermediate`, `advanced`).
- **Status**: The current status of the course (values: `upcoming`, `recorded`, `running`).
- **Start Date**: The start date of the course.
- **Teacher**: The teacher assigned to the course.
- **Number of Lessons**: The number of lessons in the course.
- **Course Thumbnail**: Thumbnail image for the course.
- **Preview Video**: A video showing a preview of the course.

#### 2.1. Scholarship
Each course can have scholarships associated with it. Scholarship fields include:
- **Name**
- **Email**
- **Phone Number**
- **Address**
- **Current Level of Study**: (values: `high school`, `undergrad`, `postgrad`, `other`)
- **Field of Study/Major**
- **Why are you applying for the scholarship?** (text field)
- **How will the scholarship help you achieve your goals?** (text field)
- **Upload Personal Statement/Motivation Letter**: (file upload)
- **Agree to be contacted for further discussion** (checkbox, mandatory)

#### 2.2. Curriculum
Each course will have a curriculum with modules. Each module has lessons, and each lesson can have different types of content (video, document, quiz, assignment, external link).

- **Module Fields**:
  - **Title**: The title of the module.

- **Lesson Fields**:
  - **Lesson Title**: The title of the lesson.
  - **Content Type**: Type of content (video, document, quiz, assignment, external link).
  - **Content**: Actual content of the lesson based on the content type.
  
  For **Quiz** lesson type:
  - **Time Limit**: The time limit for the quiz in minutes.
  - **Passing Score**: The passing score percentage.
  - **Description**: A description of the quiz.
  - **Questions**: The questions for the quiz. Each question has:
    - **Question Text**
    - **Options**
    - **Points**
    - **Correct Answer**

  For **Assignment** lesson type:
  - **Description**: Assignment description.
  - **Instructions**: Instructions for the assignment.
  - **Due Date**: The assignment’s due date.
  - **Max Points**: The maximum points for the assignment.
  - **Allowed File Types**: File types allowed for submission.
  - **Max File Size**: The max file size allowed for the assignment (in MB).

**Note**: Teachers or admins can grade open-ended questions manually, while fixed-answer quizzes will be auto-graded.

---

### 3. Consultations
The **admin** can create consultations where they can:
- Select the teacher for consultation.
- Create time slots for consultations by selecting the day, start time, and end time.
- Integrate Zoom for virtual consultations.
  
The admin can also create **bundles** for consultations with discounts. Bundle fields include:
- **Number of Sessions**: How many sessions are included in the bundle.
- **Original Hourly Rate**: The teacher's original hourly rate.
- **Discount Percentage**: The discount percentage for the bundle.
- **Final Hourly Rate**: The discounted hourly rate after applying the discount percentage.

---

## Next Steps for AI Agent

- **Environment Setup**: Set up the environment using the virtual environment path `/home/samin/projects/zahra/venv`.
- **Package Installation**: Continuously scan the `requirements.txt` to check and install necessary packages.
- **Django Models and Migrations**: Define the models for users, courses, consultations, and scholarships in Django. Implement migrations.
- **Authentication**: Implement authentication using Djoser and SimpleJWT for secure user management.
- **Course Management**: Create functionality for admins to manage courses, including course creation, curriculum setup, and teacher assignment.
- **Consultation Scheduling**: Implement consultation scheduling and integration with Zoom API.
- **Scholarship Application**: Set up a form for students to apply for scholarships, including validation for required fields and file upload handling.

---