from django.db import models

from accounts.models import User
from books.models import Book
from courses.models import Bundle, Course


class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="cart")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_total(self):
        return sum(item.get_total_price() for item in self.items.all())

    def has_physical_items(self):
        return self.items.filter(item_type=CartItem.ItemType.PHYSICAL_BOOK).exists()

    def __str__(self):
        return f"Cart of {self.user.email}"


class CartItem(models.Model):
    class ItemType(models.TextChoices):
        COURSE = "course", "Course"
        BUNDLE = "bundle", "Bundle"
        DIGITAL_BOOK = "digital_book", "Digital Book"
        PHYSICAL_BOOK = "physical_book", "Physical Book"

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    item_type = models.CharField(max_length=15, choices=ItemType.choices)

    # Only one will be set per item
    course = models.ForeignKey(Course, null=True, blank=True, on_delete=models.CASCADE)
    bundle = models.ForeignKey(Bundle, null=True, blank=True, on_delete=models.CASCADE)
    book = models.ForeignKey(Book, null=True, blank=True, on_delete=models.CASCADE)

    quantity = models.PositiveIntegerField(default=1)  # only relevant for physical books
    added_at = models.DateTimeField(auto_now_add=True)

    def get_total_price(self):
        if self.item_type == self.ItemType.COURSE:
            return self.course.price * self.quantity
        elif self.item_type == self.ItemType.BUNDLE:
            return self.bundle.price * self.quantity
        elif self.item_type == self.ItemType.DIGITAL_BOOK:
            return self.book.digital_price * self.quantity
        elif self.item_type == self.ItemType.PHYSICAL_BOOK:
            return self.book.physical_price * self.quantity
        return 0

    def get_unit_price(self):
        if self.item_type == self.ItemType.COURSE:
            return self.course.price
        elif self.item_type == self.ItemType.BUNDLE:
            return self.bundle.price
        elif self.item_type == self.ItemType.DIGITAL_BOOK:
            return self.book.digital_price
        elif self.item_type == self.ItemType.PHYSICAL_BOOK:
            return self.book.physical_price
        return 0

    def get_display_name(self):
        if self.item_type == self.ItemType.COURSE:
            return self.course.title
        elif self.item_type == self.ItemType.BUNDLE:
            return self.bundle.name
        else:
            return self.book.title

    def __str__(self):
        return f"{self.item_type} item in cart of {self.cart.user.email}"


class Order(models.Model):
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class OrderType(models.TextChoices):
        DIRECT = "direct", "Direct"  # course, bundle, digital book
        CART = "cart", "Cart"  # physical books

    class FulfillmentStatus(models.TextChoices):
        NOT_APPLICABLE = "not_applicable", "Not Applicable"  # digital orders
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")
    order_type = models.CharField(max_length=10, choices=OrderType.choices)
    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    fulfillment_status = models.CharField(
        max_length=20,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.NOT_APPLICABLE,
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_reference = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order #{self.id} by {self.user.email} — {self.status}"

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user"], name="order_user_idx"),
            models.Index(fields=["user", "status"], name="order_user_status_idx"),
        ]


class OrderItem(models.Model):
    ITEM_TYPE_CHOICES = (
        ("course", "Course"),
        ("bundle", "Bundle"),
        ("digital_book", "Digital Book"),
        ("physical_book", "Physical Book"),
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    item_type = models.CharField(max_length=15, choices=ITEM_TYPE_CHOICES)

    # Only one will be set per item
    course = models.ForeignKey(Course, null=True, blank=True, on_delete=models.SET_NULL)
    bundle = models.ForeignKey(
        "courses.Bundle", null=True, blank=True, on_delete=models.SET_NULL
    )
    book = models.ForeignKey(Book, null=True, blank=True, on_delete=models.SET_NULL)

    quantity = models.PositiveIntegerField(
        default=1
    )  # only relevant for physical books

    # Price snapshot at time of purchase
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    # Lulu print-on-demand tracking
    lulu_print_job_id = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.item_type} item in Order #{self.order.id}"


class ShippingAddress(models.Model):
    order = models.OneToOneField(
        Order, on_delete=models.CASCADE, related_name="shipping_address"
    )
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    address_line = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return f"Shipping address for Order #{self.order.id}"
