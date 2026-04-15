from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "admin"


class IsTeacherRole(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "teacher"


class IsAdminOrTeacher(BasePermission):
    """Allows access to admin or teacher roles."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ("admin", "teacher")


class IsStudent(BasePermission):
    """Allows access only to authenticated users with the student role."""
    message = "Only students can perform this action."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "student"
