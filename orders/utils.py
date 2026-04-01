from .models import OrderItem


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
        return qs.filter(item_type='course', course=obj).exists()

    elif isinstance(obj, Book):
        if format == 'digital':
            return qs.filter(item_type='digital_book', book=obj).exists()
        elif format == 'physical':
            return qs.filter(item_type='physical_book', book=obj).exists()

    return False


def already_owns(user, obj, format=None):
    return has_access(user, obj, format=format)