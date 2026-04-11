from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import serializers, status
from email_templates.sendgrid import send_email, send_plain_email


class ContactSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    message = serializers.CharField()


@api_view(["POST"])
@permission_classes([AllowAny])
def contact_view(request):
    serializer = ContactSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    recipient = getattr(settings, "CONTACT_EMAIL", settings.DEFAULT_FROM_EMAIL)
    template_data = {
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "email": data["email"],
        "message": data["message"],
    }

    sent = send_email(
        to_email=recipient,
        purpose="contact",
        template_data=template_data,
    )
    if not sent:
        plain_body = (
            f"New contact form submission\n\n"
            f"Name: {data['first_name']} {data['last_name']}\n"
            f"Email: {data['email']}\n\n"
            f"Message:\n{data['message']}"
        )
        send_plain_email(
            to_email=recipient,
            subject=f"Contact from {data['first_name']} {data['last_name']}",
            body=plain_body,
        )

    return Response({"detail": "Your message has been sent."}, status=status.HTTP_200_OK)
