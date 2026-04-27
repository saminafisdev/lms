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
from config.tasks import sync_newsletter_contact_task

from .models import StudentProfile, TeacherProfile, NewsletterSubscriber
from .permissions import IsTeacher
from .serializers import (
    StudentProfileSerializer,
    StudentProfileMeSerializer,
    TeacherProfileSerializer,
    NewsletterSubscribeSerializer,
    NewsletterSubscriberSerializer,
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

    @action(detail=False, methods=["get", "patch"], url_path="me", permission_classes=[IsAuthenticated])
    def me(self, request):
        try:
            profile = request.user.student_profile
        except StudentProfile.DoesNotExist:
            return Response({"detail": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.method == "PATCH":
            serializer = StudentProfileMeSerializer(profile, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            old_subscribed = profile.is_subscribed_to_newsletter
            profile = serializer.save()
            new_subscribed = profile.is_subscribed_to_newsletter
            if not old_subscribed and new_subscribed:
                add_contact(profile.user)
            elif old_subscribed and not new_subscribed:
                remove_contact(profile.user)
            return Response(serializer.data)

        return Response(StudentProfileMeSerializer(profile).data)

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
        sync_newsletter_contact_task.delay(
            request.user.email, "subscribe",
            first_name=request.user.first_name or "",
            last_name=request.user.last_name or "",
        )
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
        sync_newsletter_contact_task.delay(request.user.email, "unsubscribe")
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
        from orders.models import Order, OrderItem
        from orders.serializers import OrderSerializer
        from books.models import Book
        from books.serializers import PurchasedBookSerializer
        from consultations.models import AvailableTimeslot
        from consultations.serializers import AvailableTimeslotSerializer

        user = request.user
        now = timezone.now()

        # My courses (enrollments) — single query with all relations
        enrollments = list(
            Enrollment.objects.filter(user=user)
            .select_related("course", "course__teacher", "course__teacher__user", "course__category")
        )

        # My books (purchased digital books) — select_related for category avoids N+1
        book_ids = OrderItem.objects.filter(
            order__user=user,
            order__status="completed",
            item_type="digital_book",
        ).values_list("book_id", flat=True).distinct()
        books = list(Book.objects.filter(id__in=book_ids).select_related("category"))

        # My orders — prefetch items and shipping_address to avoid N+1
        orders = list(
            Order.objects.filter(user=user)
            .prefetch_related("items", "shipping_address")
            .order_by("-created_at")[:10]
        )

        # Upcoming consultation sessions
        upcoming_sessions = list(
            AvailableTimeslot.objects.filter(
                purchases__student=user,
                purchases__status="completed",
                scheduled_start__gte=now,
            )
            .select_related("consultation", "consultation__teacher", "consultation__teacher__user")
            .order_by("scheduled_start")[:5]
        )

        # Next live class from enrolled courses
        enrolled_course_ids = [e.course_id for e in enrollments]
        next_live = (
            Lesson.objects.filter(
                module__course_id__in=enrolled_course_ids,
                content_type="live",
                scheduled_at__gte=now,
            )
            .select_related("module", "module__course")
            .order_by("scheduled_at")
            .first()
        )

        # Stats — reuse already-fetched data, no extra COUNT queries
        stats = {
            "total_active_courses": len(enrollments),
            "total_books": len(books),
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


class NewsletterSubscribeView(APIView):
    """POST /newsletter/subscribe/ — public, no auth required."""
    permission_classes = [permissions.AllowAny]

    @extend_schema(request=NewsletterSubscribeSerializer, responses={200: None})
    def post(self, request):
        serializer = NewsletterSubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        subscriber, created = NewsletterSubscriber.objects.get_or_create(email=email)
        if not created and subscriber.is_active:
            # Already subscribed in DB — re-sync to SendGrid in case it was missed
            sync_newsletter_contact_task.delay(email, "subscribe")
            return Response({"detail": "Already subscribed."})
        subscriber.is_active = True
        subscriber.save(update_fields=["is_active"])
        sync_newsletter_contact_task.delay(email, "subscribe")
        return Response({"detail": "Successfully subscribed to newsletter."})


class NewsletterUnsubscribeView(APIView):
    """POST /newsletter/unsubscribe/ — public, no auth required."""
    permission_classes = [permissions.AllowAny]

    @extend_schema(request=NewsletterSubscribeSerializer, responses={200: None})
    def post(self, request):
        serializer = NewsletterSubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        updated = NewsletterSubscriber.objects.filter(email=email).update(is_active=False)
        if not updated:
            return Response({"detail": "Email not found."}, status=status.HTTP_404_NOT_FOUND)
        sync_newsletter_contact_task.delay(email, "unsubscribe")
        return Response({"detail": "Successfully unsubscribed."})


class NewsletterSubscriberViewSet(viewsets.ViewSet):
    """Admin-only — manage newsletter subscribers."""
    permission_classes = [IsAdminRole]

    @extend_schema(responses={200: NewsletterSubscriberSerializer(many=True)})
    def list(self, request):
        """GET /newsletter/subscribers/ — list all subscribers."""
        from config.pagination import StandardPagination
        active_only = request.query_params.get("active")
        qs = NewsletterSubscriber.objects.all()
        if active_only == "true":
            qs = qs.filter(is_active=True)
        elif active_only == "false":
            qs = qs.filter(is_active=False)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            NewsletterSubscriberSerializer(page, many=True).data
        )

    @extend_schema(responses={204: None})
    def destroy(self, request, pk=None):
        """DELETE /newsletter/subscribers/{id}/ — remove a subscriber."""
        try:
            subscriber = NewsletterSubscriber.objects.get(pk=pk)
        except NewsletterSubscriber.DoesNotExist:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        subscriber.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminDashboardView(APIView):
    """GET /admin/dashboard/ — summary stats for the admin."""
    permission_classes = [IsAdminRole]

    def get(self, request):
        from django.db.models import Sum, Count
        from django.utils import timezone
        from orders.models import Order, OrderItem
        from courses.models import Course, Enrollment, Lesson

        User = request.user.__class__

        # --- Stats ---
        total_students = User.objects.filter(role="student").count()
        total_teachers = User.objects.filter(role="teacher").count()
        active_courses = Course.objects.filter(is_active=True).count()
        total_revenue = (
            Order.objects.filter(status=Order.PaymentStatus.COMPLETED)
            .aggregate(total=Sum("total_amount"))["total"]
            or 0
        )

        # --- Top 5 courses by revenue ---
        top_course_items = (
            OrderItem.objects.filter(
                item_type="course",
                order__status=Order.PaymentStatus.COMPLETED,
            )
            .values("course")
            .annotate(revenue=Sum("total_price"), student_count=Count("order__user", distinct=True))
            .order_by("-revenue")[:5]
        )
        course_ids = [row["course"] for row in top_course_items]
        courses_map = {
            c.id: c
            for c in Course.objects.filter(id__in=course_ids).select_related("teacher__user")
        }
        top_courses_data = []
        for row in top_course_items:
            course = courses_map.get(row["course"])
            if not course:
                continue
            teacher = course.teacher
            instructor_name = (
                teacher.user.get_full_name() or teacher.user.email
                if teacher and teacher.user
                else "—"
            )
            top_courses_data.append({
                "id": course.id,
                "title": course.title,
                "instructor": instructor_name,
                "student_count": row["student_count"],
                "revenue": row["revenue"],
            })

        # --- Today's scheduled live classes ---
        today = timezone.localdate()
        todays_classes = (
            Lesson.objects.filter(content_type="live", scheduled_at__date=today)
            .select_related("module__course__teacher__user")
            .order_by("scheduled_at")
        )
        todays_classes_data = []
        for lesson in todays_classes:
            course = lesson.module.course
            teacher = course.teacher
            instructor_name = (
                teacher.user.get_full_name() or teacher.user.email
                if teacher and teacher.user
                else "—"
            )
            todays_classes_data.append({
                "lesson_id": lesson.id,
                "title": lesson.title,
                "course_title": course.title,
                "instructor": instructor_name,
                "scheduled_at": lesson.scheduled_at,
                "zoom_join_url": lesson.zoom_join_url,
            })

        return Response({
            "stats": {
                "total_students": total_students,
                "total_teachers": total_teachers,
                "active_courses": active_courses,
                "total_revenue": total_revenue,
            },
            "top_courses": top_courses_data,
            "todays_classes": todays_classes_data,
        })


class TeacherEarningsView(APIView):
    """GET /dashboard/teacher-earnings/ — per-teacher revenue breakdown (admin only)."""
    permission_classes = [IsAdminRole]

    def get(self, request):
        from django.db.models import Sum, Count
        from orders.models import Order, OrderItem
        from consultations.models import ConsultationPurchase

        teachers = TeacherProfile.objects.select_related("user").all()
        results = []

        for teacher in teachers:
            # Course revenue from completed orders
            course_revenue = (
                OrderItem.objects.filter(
                    item_type="course",
                    course__teacher=teacher,
                    order__status=Order.PaymentStatus.COMPLETED,
                ).aggregate(total=Sum("total_price"))["total"]
                or 0
            )

            # Consultation revenue from completed purchases
            consultation_revenue = (
                ConsultationPurchase.objects.filter(
                    consultation__teacher=teacher,
                    status="completed",
                ).aggregate(total=Sum("total_price_paid"))["total"]
                or 0
            )

            # Distinct enrolled students across all courses
            student_count = (
                OrderItem.objects.filter(
                    item_type="course",
                    course__teacher=teacher,
                    order__status=Order.PaymentStatus.COMPLETED,
                ).aggregate(count=Count("order__user", distinct=True))["count"]
                or 0
            )

            # Completed consultation sessions
            session_count = ConsultationPurchase.objects.filter(
                consultation__teacher=teacher,
                status="completed",
            ).count()

            results.append({
                "teacher_id": teacher.id,
                "name": teacher.user.get_full_name() or teacher.user.email,
                "email": teacher.user.email,
                "course_revenue": course_revenue,
                "consultation_revenue": consultation_revenue,
                "total_earnings": course_revenue + consultation_revenue,
                "student_count": student_count,
                "session_count": session_count,
            })

        # Sort by total earnings descending
        results.sort(key=lambda x: x["total_earnings"], reverse=True)
        return Response(results)
