from django.db import models
from django.utils.text import slugify
from django_resized import ResizedImageField
from accounts.models import TeacherProfile


class CourseCategory(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Course Categories"


class Course(models.Model):
    LEVEL_CHOICES = (
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    )
    STATUS_CHOICES = (
        ("upcoming", "Upcoming"),
        ("recorded", "Recorded"),
        ("running", "Running"),
    )

    category = models.ForeignKey(
        CourseCategory, on_delete=models.SET_NULL, null=True, related_name="courses"
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    subtitle = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField()
    price = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Price in USD"
    )
    duration_in_weeks = models.PositiveSmallIntegerField(help_text="Number of weeks")
    hours_per_session = models.DecimalField(max_digits=5, decimal_places=2)
    total_hours = models.DecimalField(max_digits=5, decimal_places=2)
    level = models.CharField(max_length=15, choices=LEVEL_CHOICES, default="beginner")
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="upcoming")
    start_date = models.DateField(blank=True, null=True)
    teacher = models.ForeignKey(
        TeacherProfile, on_delete=models.SET_NULL, null=True, related_name="courses"
    )
    is_active = models.BooleanField(
        default=True, help_text="Active courses are visible to students"
    )
    thumbnail = ResizedImageField(
        size=[800, 600],
        crop=["middle", "center"],
        quality=100,
        upload_to="courses/thumbnails/",
        force_format="WEBP",
        blank=True,
        null=True,
    )
    preview_video = models.FileField(
        upload_to="courses/previews/", blank=True, null=True
    )

    def __str__(self):
        return self.title


class Enrollment(models.Model):
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="enrollments"
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="enrollments"
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    def check_completion(self):
        """
        Marks enrollment complete when all course requirements are met:
        - Quiz lessons: a passing QuizAttempt exists
        - Assignment lessons: an approved AssignmentSubmission exists
        - All other lessons: a LessonCompletion record exists
        """
        from django.utils import timezone

        lessons = Lesson.objects.filter(module__course=self.course, is_active=True)
        if not lessons.exists():
            return False

        for lesson in lessons:
            if lesson.content_type == "quiz":
                has_passed = QuizAttempt.objects.filter(
                    user=self.user, quiz__lesson=lesson, passed=True
                ).exists()
                if not has_passed:
                    return False
            elif lesson.content_type == "assignment":
                has_approved = AssignmentSubmission.objects.filter(
                    user=self.user,
                    assignment__lesson=lesson,
                    status=AssignmentSubmission.Status.APPROVED,
                ).exists()
                if not has_approved:
                    return False
            else:
                has_completed = LessonCompletion.objects.filter(
                    user=self.user, lesson=lesson
                ).exists()
                if not has_completed:
                    return False

        self.is_completed = True
        self.completed_at = timezone.now()
        self.save(update_fields=["is_completed", "completed_at"])
        return True

    @property
    def progress_percent(self):
        total = Lesson.objects.filter(module__course=self.course, is_active=True).count()
        if total == 0:
            return 0
        completed = LessonCompletion.objects.filter(
            user=self.user, lesson__module__course=self.course
        ).count()
        return round((completed / total) * 100)

    class Meta:
        unique_together = ("user", "course")
        indexes = [
            models.Index(fields=["user"], name="enrollment_user_idx"),
            models.Index(fields=["user", "is_completed"], name="enrollment_user_completed_idx"),
        ]

    def __str__(self):
        return f"{self.user.email} enrolled in {self.course.title}"


class Bundle(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    courses = models.ManyToManyField(Course, related_name="bundles", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Scholarship(models.Model):
    LEVEL_CHOICES = (
        ("high school", "High School"),
        ("undergrad", "Undergraduate"),
        ("postgrad", "Postgraduate"),
        ("other", "Other"),
    )
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scholarship_applications",
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="scholarships"
    )
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone_number = models.CharField(max_length=20)
    address = models.TextField()
    current_level_of_study = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    field_of_study = models.CharField(max_length=255)
    why_applying = models.TextField(
        verbose_name="Why are you applying for the scholarship?"
    )
    how_will_it_help = models.TextField(
        verbose_name="How will the scholarship help you achieve your goals?"
    )
    agree_to_contact = models.BooleanField(
        default=False, verbose_name="Agree to be contacted for further discussion"
    )

    # Admin-set fields
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Discount percentage granted on approval (e.g. 50.00 for 50%)",
    )
    rejection_note = models.TextField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_scholarships",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} - {self.course.title} ({self.status})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.agree_to_contact:
            raise ValidationError(
                "You must agree to be contacted for further discussion."
            )


class ScholarshipDocument(models.Model):
    scholarship = models.ForeignKey(
        Scholarship, on_delete=models.CASCADE, related_name="documents"
    )
    file = models.FileField(upload_to="scholarships/documents/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Document for {self.scholarship}"


class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        unique_together = ["course", "order"]

    def __str__(self):
        return f"{self.course.title} - {self.title}"


class Lesson(models.Model):
    CONTENT_TYPE_CHOICES = (
        ("video", "Video"),
        ("document", "Document"),
        ("quiz", "Quiz"),
        ("assignment", "Assignment"),
        ("external_link", "External Link"),
        ("live", "Live Session"),
    )

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=255)
    content_type = models.CharField(max_length=15, choices=CONTENT_TYPE_CHOICES)
    content = models.TextField(
        blank=True, null=True, help_text="Text content or external link URL"
    )
    file_content = models.FileField(upload_to="lessons/files/", blank=True, null=True)
    video_content = models.FileField(upload_to="lessons/videos/", blank=True, null=True)
    duration_in_minutes = models.PositiveIntegerField(
        default=0, help_text="Duration in minutes"
    )
    is_preview = models.BooleanField(
        default=False, help_text="If True, this lesson is available for free preview."
    )
    is_released = models.BooleanField(
        default=False,
        help_text="Non-live lessons: mark as released to unlock for enrolled students."
    )
    order = models.PositiveIntegerField(default=0)

    # Bunny Stream video fields
    bunny_video_id = models.CharField(max_length=100, blank=True, default="")
    bunny_video_status = models.CharField(max_length=20, blank=True, default="")

    # Live session / Zoom fields
    scheduled_at = models.DateTimeField(
        null=True, blank=True, help_text="Start time for live sessions (UTC)"
    )
    zoom_meeting_id = models.CharField(max_length=255, blank=True, null=True)
    zoom_join_url = models.URLField(max_length=1000, blank=True, null=True)
    zoom_start_url = models.URLField(max_length=1000, blank=True, null=True)

    class Meta:
        ordering = ["order"]
        unique_together = ["module", "order"]

    def __str__(self):
        return self.title


class Quiz(models.Model):
    lesson = models.OneToOneField(
        Lesson, on_delete=models.CASCADE, related_name="quiz_details"
    )
    time_limit = models.PositiveIntegerField(help_text="Time limit in minutes")
    passing_score = models.PositiveIntegerField(
        help_text="Passing score percentage (0-100)"
    )
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Quiz for {self.lesson.title}"


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    points = models.PositiveIntegerField(default=1)

    def __str__(self):
        return self.text


class Option(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="options"
    )
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text


class Assignment(models.Model):
    lesson = models.OneToOneField(
        Lesson, on_delete=models.CASCADE, related_name="assignment_details"
    )
    description = models.TextField()
    instructions = models.TextField()
    due_date = models.DateTimeField()
    max_points = models.PositiveIntegerField(default=100)
    allowed_file_types = models.CharField(
        max_length=255, help_text="e.g., pdf, docx, zip"
    )
    max_file_size = models.PositiveIntegerField(help_text="Max file size in MB")

    def __str__(self):
        return f"Assignment for {self.lesson.title}"


class LessonCompletion(models.Model):
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="lesson_completions"
    )
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, related_name="completions"
    )
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "lesson")

    def __str__(self):
        return f"{self.user.email} completed {self.lesson.title}"


class QuizAttempt(models.Model):
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="quiz_attempts"
    )
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    score = models.DecimalField(
        max_digits=5, decimal_places=2, help_text="Score as percentage 0–100"
    )
    passed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} – {self.quiz} – {self.score}%"


class QuizAnswer(models.Model):
    attempt = models.ForeignKey(
        QuizAttempt, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(Option, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("attempt", "question")


class AssignmentSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="assignment_submissions",
    )
    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="submissions"
    )
    submission_text = models.TextField(blank=True, null=True)
    submission_file = models.FileField(
        upload_to="courses/submissions/", blank=True, null=True
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    teacher_feedback = models.TextField(blank=True, null=True)
    mark = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_submissions",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} – {self.assignment}"
