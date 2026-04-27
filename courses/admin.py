from django.contrib import admin
from .models import (
    Course,
    CourseCategory,
    Scholarship,
    Module,
    Lesson,
    Quiz,
    Question,
    Option,
    Assignment,
    Enrollment,
    QuizAttempt,
    AssignmentSubmission,
)

admin.site.register(Course)
admin.site.register(CourseCategory)
admin.site.register(Scholarship)
admin.site.register(Module)


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "content_type", "module", "order", "is_preview", "is_released", "is_downloadable")
    list_filter = ("content_type", "is_released")


admin.site.register(Quiz)
admin.site.register(Question)
admin.site.register(Option)
admin.site.register(Assignment)
admin.site.register(Enrollment)


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "quiz", "score", "passed", "created_at")
    list_filter = ("passed",)
    search_fields = ("user__email",)
    readonly_fields = ("user", "quiz", "score", "passed", "created_at")


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ("user", "assignment", "status", "mark", "reviewed_by", "created_at")
    list_filter = ("status",)
    search_fields = ("user__email",)
    readonly_fields = ("user", "assignment", "submission_text", "submission_file", "created_at", "updated_at")
    fields = (
        "user", "assignment", "submission_text", "submission_file",
        "status", "teacher_feedback", "mark", "reviewed_by", "reviewed_at",
        "created_at", "updated_at",
    )
