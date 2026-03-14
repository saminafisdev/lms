from rest_framework import serializers
from accounts.serializers import TeacherProfileSerializer
from .models import Consultation, AvailableTimeslot, Bundle, ConsultationPurchase

class AvailableTimeslotSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailableTimeslot
        fields = "__all__"

class BundleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bundle
        fields = "__all__"

class ConsultationSerializer(serializers.ModelSerializer):
    teacher = TeacherProfileSerializer(read_only=True)
    teacher_id = serializers.IntegerField(write_only=True)
    timeslots = AvailableTimeslotSerializer(many=True, read_only=True)
    bundles = BundleSerializer(many=True, read_only=True)

    class Meta:
        model = Consultation
        fields = "__all__"

class ConsultationPurchaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsultationPurchase
        fields = "__all__"
        read_only_fields = ["total_price_paid", "bundle_applied", "student"]
