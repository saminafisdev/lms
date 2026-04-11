from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


def _choices(pairs):
    return [{"value": v, "label": l} for v, l in pairs]


@api_view(["GET"])
@permission_classes([AllowAny])
def choices_view(request):
    """
    GET /choices/
    Returns all enum/choice options used across the platform.
    Frontend should fetch this once on app load.
    """
    return Response({
        "course": {
            "level": _choices([
                ("beginner", "Beginner"),
                ("intermediate", "Intermediate"),
                ("advanced", "Advanced"),
            ]),
            "status": _choices([
                ("upcoming", "Upcoming"),
                ("recorded", "Recorded"),
                ("running", "Running"),
            ]),
            "lesson_content_type": _choices([
                ("video", "Video"),
                ("document", "Document"),
                ("quiz", "Quiz"),
                ("assignment", "Assignment"),
                ("external_link", "External Link"),
            ]),
        },
        "scholarship": {
            "level_of_study": _choices([
                ("high school", "High School"),
                ("undergrad", "Undergraduate"),
                ("postgrad", "Postgraduate"),
                ("other", "Other"),
            ]),
            "status": _choices([
                ("pending", "Pending"),
                ("approved", "Approved"),
                ("rejected", "Rejected"),
            ]),
        },
        "order": {
            "status": _choices([
                ("pending", "Pending"),
                ("completed", "Completed"),
                ("failed", "Failed"),
            ]),
            "type": _choices([
                ("direct", "Direct"),
                ("cart", "Cart"),
            ]),
            "item_type": _choices([
                ("course", "Course"),
                ("bundle", "Bundle"),
                ("digital_book", "Digital Book"),
                ("physical_book", "Physical Book"),
            ]),
        },
        "user": {
            "role": _choices([
                ("admin", "Admin"),
                ("teacher", "Teacher"),
                ("student", "Student"),
            ]),
        },
        "blog": {
            "status": _choices([
                ("draft", "Draft"),
                ("pending", "Pending Approval"),
                ("published", "Published"),
                ("rejected", "Rejected"),
            ]),
        },
        "video": {
            "status": _choices([
                ("draft", "Draft"),
                ("pending", "Pending Approval"),
                ("published", "Published"),
                ("rejected", "Rejected"),
            ]),
        },
        "review": {
            "type": _choices([
                ("course", "Course"),
                ("book", "Book"),
                ("consultation", "Consultation"),
            ]),
            "rating": _choices([(str(i), f"{i} Star{'s' if i > 1 else ''}") for i in range(1, 6)]),
        },
    })
