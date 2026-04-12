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
)

admin.site.register(Course)
admin.site.register(CourseCategory)
admin.site.register(Scholarship)
admin.site.register(Module)


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "content_type", "module", "order", "is_preview")
    list_filter = ("content_type",)


admin.site.register(Quiz)
admin.site.register(Question)
admin.site.register(Option)
admin.site.register(Assignment)
admin.site.register(Enrollment)
