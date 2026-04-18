from django.utils import timezone
from rest_framework import permissions
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import fields as drf_fields
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser

from config.sendgrid_contacts import add_contact, remove_contact
from config.permissions import IsAdminRole

from .models import StudentProfile, TeacherProfile
from .permissions import IsTeacher
from .serializers import (
    StudentProfileSerializer,
    TeacherProfileSerializer,
)


class TeacherProfileViewSet(viewsets.ModelViewSet):
    queryset = TeacherProfile.objects.all()
    serializer_class = TeacherProfileSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["professional_title", "location", "offers_consultations"]
    search_fields = [
        "user__first_name",
        "user__last_name",
        "user__email",
        "professional_title",
        "location",
        "about",
    ]

    def get_parsers(self):
        # create requires JSON (nested user object can't be represented in multipart)
        # update/partial_update allow multipart for profile picture uploads
        if getattr(self, "action", None) == "create":
            return [JSONParser()]
        return [MultiPartParser(), FormParser(), JSONParser()]

    def get_permissions(self):
        if self.action == "destroy":
            return [IsAdminRole()]
        return [permissions.AllowAny()]

    def perform_destroy(self, instance):
        # Deleting the user cascades and removes the teacher profile too
        instance.user.delete()

    @action(
        detail=False,
        methods=["get"],
        url_path="me",
        permission_classes=[IsAuthenticated, IsTeacher],
    )
    def me(self, request):
        try:
            teacher = request.user.teacher_profile
        except TeacherProfile.DoesNotExist:
            return Response(
                {"detail": "Teacher profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.get_serializer(teacher)
        return Response(serializer.data)


class StudentProfileViewSet(viewsets.ModelViewSet):
    queryset = StudentProfile.objects.all()
    serializer_class = StudentProfileSerializer
    # permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        profile = serializer.save()
        if profile.is_subscribed_to_newsletter:
            add_contact(profile.user)

    def perform_update(self, serializer):
        old_subscribed = self.get_object().is_subscribed_to_newsletter
        profile = serializer.save()
        new_subscribed = profile.is_subscribed_to_newsletter

        if not old_subscribed and new_subscribed:
            add_contact(profile.user)
        elif old_subscribed and not new_subscribed:
            remove_contact(profile.user)

    @action(
        detail=False,
        methods=["post"],
        url_path="newsletter/subscribe",
        permission_classes=[permissions.IsAuthenticated],
    )
    def newsletter_subscribe(self, request):
        profile = getattr(request.user, "student_profile", None)
        if not profile:
            return Response(
                {"error": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        profile.is_subscribed_to_newsletter = True
        profile.save(update_fields=["is_subscribed_to_newsletter"])
        add_contact(request.user)
        return Response({"detail": "Subscribed to newsletter."})

    @action(
        detail=False,
        methods=["post"],
        url_path="newsletter/unsubscribe",
        permission_classes=[permissions.IsAuthenticated],
    )
    def newsletter_unsubscribe(self, request):
        profile = getattr(request.user, "student_profile", None)
        if not profile:
            return Response(
                {"error": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        profile.is_subscribed_to_newsletter = False
        profile.save(update_fields=["is_subscribed_to_newsletter"])
        remove_contact(request.user)
        return Response({"detail": "Unsubscribed from newsletter."})


class StudentDashboardView(APIView):
    """
    GET /student/dashboard/
    Returns a summary for the authenticated student's dashboard.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: inline_serializer(
                name="StudentDashboard",
                fields={
                    "stats": inline_serializer(
                        name="StudentDashboardStats",
                        fields={
                            "total_active_courses": drf_fields.IntegerField(),
                            "total_books": drf_fields.IntegerField(),
                            "total_orders": drf_fields.IntegerField(),
                        },
                    ),
                    "my_courses": drf_fields.ListField(),
                    "my_books": drf_fields.ListField(),
                    "my_orders": drf_fields.ListField(),
                    "upcoming_sessions": drf_fields.ListField(),
                    "next_live_class": drf_fields.DictField(allow_empty=True),
                },
            )
        },
        summary="Student dashboard — stats, courses, books, orders, upcoming sessions, next live class",
    )
    def get(self, request):
        from courses.models import Enrollment, Lesson
        from courses.serializers import EnrollmentSerializer, LessonSerializer
        from orders.models import Order
        from orders.serializers import OrderSerializer
        from books.models import Book
        from books.serializers import PurchasedBookSerializer
        from orders.models import OrderItem
        from consultations.models import ConsultationPurchase, AvailableTimeslot
        from consultations.serializers import ConsultationPurchaseSerializer, AvailableTimeslotSerializer

        user = request.user
        now = timezone.now()

        # My courses (enrollments)
        enrollments = (
            Enrollment.objects.filter(user=user)
            .select_related("course", "course__teacher", "course__teacher__user", "course__category")
        )

        # My books (purchased digital books)
        book_ids = OrderItem.objects.filter(
            order__user=user,
            order__status="completed",
            item_type="digital_book",
        ).values_list("book_id", flat=True).distinct()
        books = Book.objects.filter(id__in=book_ids)

        # My orders
        orders = Order.objects.filter(user=user).order_by("-created_at")[:10]

        # Upcoming consultation sessions (booked slots in the future)
        upcoming_sessions = (
            AvailableTimeslot.objects.filter(
                purchases__student=user,
                purchases__status="confirmed",
                start_time__gte=now,
            )
            .select_related("consultation", "consultation__teacher", "consultation__teacher__user")
            .order_by("start_time")[:5]
        )

        # Next live class from enrolled courses
        enrolled_course_ids = enrollments.values_list("course_id", flat=True)
        next_live = (
            Lesson.objects.filter(
                module__course_id__in=enrolled_course_ids,
                content_type="live",
                scheduled_at__gte=now,
                is_released=True,
            )
            .select_related("module", "module__course")
            .order_by("scheduled_at")
            .first()
        )

        # Stats
        stats = {
            "total_active_courses": enrollments.count(),
            "total_books": books.count(),
            "total_orders": Order.objects.filter(user=user).count(),
        }

        return Response({
            "stats": stats,
            "my_courses": EnrollmentSerializer(enrollments, many=True, context={"request": request}).data,
            "my_books": PurchasedBookSerializer(books, many=True, context={"request": request}).data,
            "my_orders": OrderSerializer(orders, many=True, context={"request": request}).data,
            "upcoming_sessions": AvailableTimeslotSerializer(upcoming_sessions, many=True, context={"request": request}).data,
            "next_live_class": LessonSerializer(next_live, context={"request": request}).data if next_live else None,
        })
