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
)

admin.site.register(Course)
admin.site.register(CourseCategory)
admin.site.register(Scholarship)
admin.site.register(Module)
admin.site.register(Lesson)
admin.site.register(Quiz)
admin.site.register(Question)
admin.site.register(Option)
admin.site.register(Assignment)
