from django.db import models
from django_resized import ResizedImageField
from accounts.models import TeacherProfile


class Category(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"


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
        Category, on_delete=models.SET_NULL, null=True, related_name="courses"
    )
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField()
    price = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Price in USD"
    )
    duration = models.PositiveSmallIntegerField(help_text="Number of weeks")
    hours_per_session = models.DecimalField(max_digits=5, decimal_places=2)
    level = models.CharField(max_length=15, choices=LEVEL_CHOICES, default="beginner")
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="upcoming")
    start_date = models.DateField(blank=True, null=True)
    teacher = models.ForeignKey(
        TeacherProfile, on_delete=models.SET_NULL, null=True, related_name="courses"
    )
    num_lessons = models.PositiveIntegerField(default=0)
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


class Scholarship(models.Model):
    LEVEL_CHOICES = (
        ("high school", "High School"),
        ("undergrad", "Undergraduate"),
        ("postgrad", "Postgraduate"),
        ("other", "Other"),
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
    personal_statement = models.FileField(upload_to="scholarships/statements/")
    agree_to_contact = models.BooleanField(
        default=False, verbose_name="Agree to be contacted for further discussion"
    )

    def __str__(self):
        return f"{self.name} - {self.course.title}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.agree_to_contact:
            raise ValidationError(
                "You must agree to be contacted for further discussion."
            )


class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.course.title} - {self.title}"


class Lesson(models.Model):
    CONTENT_TYPE_CHOICES = (
        ("video", "Video"),
        ("document", "Document"),
        ("quiz", "Quiz"),
        ("assignment", "Assignment"),
        ("external_link", "External Link"),
    )

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=255)
    content_type = models.CharField(max_length=15, choices=CONTENT_TYPE_CHOICES)
    content = models.TextField(
        blank=True, null=True, help_text="Text content or external link URL"
    )
    file_content = models.FileField(upload_to="lessons/files/", blank=True, null=True)
    video_content = models.FileField(upload_to="lessons/videos/", blank=True, null=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

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
