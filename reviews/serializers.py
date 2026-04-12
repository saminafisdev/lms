from rest_framework import serializers

from .models import Review


class ReviewWriteSerializer(serializers.Serializer):
    """Minimal schema shown in Swagger for creating/updating a review."""
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True)


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "user",
            "user_name",
            "review_type",
            "rating",
            "comment",
            "course",
            "book",
            "consultation",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "user_name", "review_type", "created_at", "updated_at"]

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.email

    def validate(self, data):
        from consultations.models import ConsultationPurchase
        from courses.models import Enrollment
        from orders.models import OrderItem

        user = self.context["request"].user
        review_type = self.context["review_type"]
        data["review_type"] = review_type

        if review_type == "course":
            course = data.get("course")
            if not course:
                raise serializers.ValidationError({"course": "Course is required."})
            if not Enrollment.objects.filter(user=user, course=course).exists():
                raise serializers.ValidationError(
                    "You must be enrolled in this course to leave a review."
                )
            data["book"] = None
            data["consultation"] = None

        elif review_type == "book":
            book = data.get("book")
            if not book:
                raise serializers.ValidationError({"book": "Book is required."})
            has_purchased = OrderItem.objects.filter(
                order__user=user,
                order__status="completed",
                book=book,
            ).exists()
            if not has_purchased:
                raise serializers.ValidationError(
                    "You must have purchased this book to leave a review."
                )
            data["course"] = None
            data["consultation"] = None

        elif review_type == "consultation":
            consultation = data.get("consultation")
            if not consultation:
                raise serializers.ValidationError(
                    {"consultation": "Consultation is required."}
                )
            has_purchased = ConsultationPurchase.objects.filter(
                student=user, consultation=consultation
            ).exists()
            if not has_purchased:
                raise serializers.ValidationError(
                    "You must have purchased this consultation to leave a review."
                )
            data["course"] = None
            data["book"] = None

        return data

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)
