from django.db import models

from accounts.models import User
from books.models import Book
from courses.models import Course


class Cart(models.Model):
    """Only used for physical books."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="cart")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_total(self):
        return sum(item.get_total_price() for item in self.items.all())

    def __str__(self):
        return f"Cart of {self.user.email}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("cart", "book")

    def get_total_price(self):
        return self.book.physical_price * self.quantity

    def __str__(self):
        return f"{self.quantity}x {self.book.title} in cart of {self.cart.user.email}"


class Order(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    )
    TYPE_CHOICES = (
        ("direct", "Direct"),  # course, bundle, digital book
        ("cart", "Cart"),  # physical books
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")
    order_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
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
