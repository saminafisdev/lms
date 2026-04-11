from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from .models import SiteSettings
from .serializers import SiteSettingsSerializer


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
