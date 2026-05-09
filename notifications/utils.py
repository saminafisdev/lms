"""
Utility to create notifications from anywhere in the codebase.

Usage:
    from notifications.utils import notify, notify_bulk

    # Single user
    notify(
        recipient=user,
        notification_type="announcement",
        title="New Announcement",
        message="Check out the latest update in your course.",
        link="/courses/5/announcements/",
    )

    # Multiple users
    notify_bulk(
        recipients=enrolled_users,
        notification_type="announcement",
        title="New Announcement",
        message="...",
        link="/courses/5/announcements/",
    )
"""

from .models import Notification, NotificationType


def notify(recipient, title, notification_type=NotificationType.GENERAL, message="", link=""):
    return Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        link=link,
    )


def notify_bulk(recipients, title, notification_type=NotificationType.GENERAL, message="", link=""):
    """Efficiently create notifications for multiple users via bulk_create."""
    notifications = [
        Notification(
            recipient=user,
            notification_type=notification_type,
            title=title,
            message=message,
            link=link,
        )
        for user in recipients
    ]
    Notification.objects.bulk_create(notifications)
