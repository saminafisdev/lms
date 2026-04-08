from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from doors.permissions import IsAdminRole
from .constants import EMAIL_TEMPLATE_VARIABLES
from .models import EmailTemplateConfig, EmailPurpose
from .serializers import EmailTemplateConfigSerializer, SendGridTemplateSerializer
from .sendgrid import fetch_sendgrid_templates


class EmailTemplateConfigViewSet(viewsets.ModelViewSet):
    """
    Admin-only viewset for managing email template mappings.
    - List/create/update which SendGrid template is used for each purpose.
    - Fetch available templates directly from SendGrid.
    """

    queryset = EmailTemplateConfig.objects.all()
    serializer_class = EmailTemplateConfigSerializer
    permission_classes = [IsAdminRole]
    pagination_class = None

    @extend_schema(responses={200: SendGridTemplateSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="sendgrid-templates")
    def sendgrid_templates(self, request):
        """
        GET /email-templates/sendgrid-templates/
        Fetches all available dynamic templates from SendGrid account.
        Admin uses this to browse templates and assign them to purposes.
        """
        templates = fetch_sendgrid_templates()
        serializer = SendGridTemplateSerializer(templates, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="purposes")
    def purposes(self, request):
        data = [
            {
                "value": choice[0],
                "label": choice[1],
                "variables": EMAIL_TEMPLATE_VARIABLES.get(choice[0], []),
            }
            for choice in EmailPurpose.choices
        ]
        return Response(data)
