from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "admin"


class IsAdminOrAuthor(BasePermission):
    """
    Admin can do anything.
    Author can only edit/delete their own video.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.user.role == "admin":
            return True
        # Check if user has a teacher profile and is the author
        teacher_profile = getattr(request.user, "teacher_profile", None)
        return teacher_profile is not None and obj.author == teacher_profile


class IsTeacherOrAdmin(BasePermission):
    """
    Only teachers (with a TeacherProfile) or admins can create video content.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.role == "admin":
            return True
        # Must have a teacher profile
        return hasattr(request.user, "teacher_profile")
