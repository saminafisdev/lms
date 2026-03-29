from rest_framework.permissions import BasePermission


class IsTeacher(BasePermission):
    message = "You do not have a teacher profile."

    def has_permission(self, request, view):
        return hasattr(request.user, "teacher_profile")
