import logging

from .models import OrderItem, Order, Cart

logger = logging.getLogger(__name__)


def has_access(user, obj, format=None):
    """
    Check if a user has completed purchase for a product.
    - format: 'digital' or 'physical' for books, None for courses
    """
    if not user.is_authenticated:
        return False

    qs = OrderItem.objects.filter(
        order__user=user,
        order__status='completed'
    )

    from courses.models import Course
    from books.models import Book

    if isinstance(obj, Course):
        from courses.models import Enrollment
        has_order = qs.filter(item_type='course', course=obj).exists()
        is_enrolled = Enrollment.objects.filter(user=user, course=obj).exists()
        return has_order and is_enrolled

    elif isinstance(obj, Book):
        if format == 'digital':
            return qs.filter(item_type='digital_book', book=obj).exists()
        elif format == 'physical':
            return qs.filter(item_type='physical_book', book=obj).exists()

    return False


def already_owns(user, obj, format=None):
    return has_access(user, obj, format=format)


def fulfill_order(order):
    """Fulfill a completed order: create enrollments, send emails, dispatch Lulu jobs."""
    from django.db import transaction
    from config.tasks import send_email_task, create_lulu_print_job_task
    from courses.models import Enrollment

    with transaction.atomic():
        for item in order.items.select_related("course", "bundle", "book").all():
            if item.item_type == "physical_book":
                item.book.stock_count -= item.quantity
                item.book.save(update_fields=["stock_count"])
                if item.book.lulu_pod_package_id and item.book.digital_file:
                    try:
                        create_lulu_print_job_task.delay(item.id)
                    except Exception as e:
                        logger.error("Failed to queue Lulu task for OrderItem %s: %s", item.id, e)

            elif item.item_type == "digital_book":
                send_email_task.delay(
                    to_email=order.user.email,
                    purpose="book_purchase",
                    template_data={
                        "first_name": order.user.first_name or "there",
                        "book_title": item.book.title,
                        "format": "Digital",
                        "amount": str(order.total_amount),
                    },
                )
                logger.info("Queued book_purchase email to %s for book %s", order.user.email, item.book.title)

            elif item.item_type == "course":
                enrollment, created = Enrollment.objects.get_or_create(user=order.user, course=item.course)
                if created:
                    from notifications.utils import notify
                    notify(
                        recipient=order.user,
                        notification_type="enrollment",
                        title=f"You're enrolled in {item.course.title}",
                        message="You now have full access to the course content.",
                        link=f"/courses/{item.course.slug}/",
                    )
                send_email_task.delay(
                    to_email=order.user.email,
                    purpose="course_purchase",
                    template_data={
                        "first_name": order.user.first_name or "there",
                        "course_name": item.course.title,
                        "amount": str(order.total_amount),
                    },
                )
                logger.info("Queued course_purchase email to %s for course %s", order.user.email, item.course.title)

            elif item.item_type == "bundle":
                bundle = item.bundle
                courses = list(bundle.courses.all())
                for course in courses:
                    enrollment, created = Enrollment.objects.get_or_create(user=order.user, course=course)
                    if created:
                        from notifications.utils import notify
                        notify(
                            recipient=order.user,
                            notification_type="enrollment",
                            title=f"You're enrolled in {course.title}",
                            message=f"Included in your {bundle.name} bundle purchase.",
                            link=f"/courses/{course.slug}/",
                        )
                course_names = ", ".join(c.title for c in courses)
                send_email_task.delay(
                    to_email=order.user.email,
                    purpose="bundle_purchase",
                    template_data={
                        "first_name": order.user.first_name or "there",
                        "bundle_name": bundle.name,
                        "course_names": course_names,
                        "amount": str(order.total_amount),
                    },
                )
                logger.info("Queued bundle_purchase email to %s for bundle %s", order.user.email, bundle.name)

        if order.order_type == Order.OrderType.CART:
            cart = Cart.objects.filter(user=order.user).first()
            if cart:
                cart.items.all().delete()

            physical_items = [i for i in order.items.all() if i.item_type == "physical_book"]
            if physical_items:
                send_email_task.delay(
                    to_email=order.user.email,
                    purpose="book_purchase",
                    template_data={
                        "first_name": order.user.first_name or "there",
                        "book_title": ", ".join(i.book.title for i in physical_items),
                        "format": "Physical",
                        "amount": str(order.total_amount),
                    },
                )
                logger.info("Queued physical book_purchase email to %s for order %s", order.user.email, order.id)