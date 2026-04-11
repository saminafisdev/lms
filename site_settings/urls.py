from django.urls import path
from .views import site_settings_detail, site_settings_update

urlpatterns = [
    path("site-settings/", site_settings_detail, name="site-settings-detail"),
    path("site-settings/update/", site_settings_update, name="site-settings-update"),
]
