from rest_framework import viewsets, permissions
from .models import Door
from .serializers import DoorSerializer, AdminDoorSerializer
from .permissions import IsAdminRole

class DoorViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing doors.
    - Public: List and retrieve visible doors.
    - Admin: Full CRUD on all doors.
    """
    queryset = Door.objects.all()
    pagination_class = None

    def get_serializer_class(self):
        """
        Return different serializer depending on user role.
        """
        user = self.request.user
        if user.is_authenticated and user.role == "admin":
            return AdminDoorSerializer
        return DoorSerializer

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.action in ["list", "retrieve"]:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [IsAdminRole]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        """
        Filter queryset based on user role and visibility.
        """
        user = self.request.user
        if user.is_authenticated and user.role == "admin":
            return Door.objects.all()
        return Door.objects.filter(is_visible=True)
