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
        if self.action == 'list':
            from django.core.cache import cache
            cached = cache.get('testimonials_active')
            if cached is None:
                cached = list(Testimonial.objects.filter(is_active=True).order_by('order'))
                cache.set('testimonials_active', cached, 60 * 60 * 24)  # 24 hours
            return cached
        return Testimonial.objects.all().order_by('order')

    def _invalidate_testimonial_cache(self):
        from django.core.cache import cache
        cache.delete('testimonials_active')

    def perform_create(self, serializer):
        serializer.save()
        self._invalidate_testimonial_cache()

    def perform_update(self, serializer):
        serializer.save()
        self._invalidate_testimonial_cache()

    def perform_destroy(self, instance):
        instance.delete()
        self._invalidate_testimonial_cache()
