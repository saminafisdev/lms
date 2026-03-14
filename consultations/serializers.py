from rest_framework import serializers
from .models import Consultation, Bundle


class ConsultationSerializer(serializers.ModelSerializer):
    teacher_email = serializers.ReadOnlyField(source="teacher.user.email")

    class Meta:
        model = Consultation
        fields = "__all__"


class BundleSerializer(serializers.ModelSerializer):
    teacher_email = serializers.ReadOnlyField(source="teacher.user.email")

    class Meta:
        model = Bundle
        fields = "__all__"
