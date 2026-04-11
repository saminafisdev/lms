from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework import status, viewsets
from .models import SiteSettings, Testimonial
from .serializers import SiteSettingsSerializer, TestimonialSerializer


@extend_schema(
    responses=SiteSettingsSerializer,
    description="Retrieve current site settings (public).",
)
@api_view(["GET"])
@permission_classes([AllowAny])
def site_settings_detail(request):
    settings_obj = SiteSettings.get()
    serializer = SiteSettingsSerializer(settings_obj)
    return Response(serializer.data)


@extend_schema(
    request=SiteSettingsSerializer,
    responses=SiteSettingsSerializer,
    description="Update site settings (admin only). All fields are optional.",
)
@api_view(["PATCH"])
@permission_classes([IsAdminUser])
def site_settings_update(request):
    settings_obj = SiteSettings.get()
    serializer = SiteSettingsSerializer(settings_obj, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_200_OK)


class TestimonialViewSet(viewsets.ModelViewSet):
    serializer_class = TestimonialSerializer
    queryset = Testimonial.objects.all()

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [IsAdminUser()]

    def get_queryset(self):
        qs = Testimonial.objects.all()
        if not (self.request.user and self.request.user.is_staff):
            qs = qs.filter(is_active=True)
        return qs
