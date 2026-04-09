from rest_framework import serializers

from books.serializers import PublicBookSerializer

from .models import Cart, CartItem, Order, OrderItem, ShippingAddress
from .utils import already_owns


class CartItemSerializer(serializers.ModelSerializer):
    book_detail = PublicBookSerializer(source="book", read_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ["id", "book", "book_detail", "quantity", "total_price", "added_at"]
        read_only_fields = ["id", "added_at"]

    def get_total_price(self, obj):
        return obj.get_total_price()

    def validate_book(self, book):
        if not book.has_physical:
            raise serializers.ValidationError(
                "This book is not available in physical format."
            )
        if book.stock_count <= 0:
            raise serializers.ValidationError("This book is out of stock.")
        return book

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        return value

    def validate(self, data):
        book = data.get("book")
        quantity = data.get("quantity", 1)
        if book and quantity > book.stock_count:
            raise serializers.ValidationError(
                {"quantity": f"Only {book.stock_count} copies available."}
            )
        return data


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "items", "total", "updated_at"]

    def get_total(self, obj):
        return obj.get_total()


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            "id",
            "item_type",
            "course",
            "book",
            "quantity",
            "unit_price",
            "total_price",
        ]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_type",
            "status",
            "total_amount",
            "items",
            "shipping_address",
            "created_at",
        ]
        read_only_fields = fields


class DirectPurchaseSerializer(serializers.Serializer):
    """For buying a course or digital book directly."""

    ITEM_TYPE_CHOICES = (
        ("course", "Course"),
        ("digital_book", "Digital Book"),
    )
    item_type = serializers.ChoiceField(choices=ITEM_TYPE_CHOICES)
    object_id = serializers.IntegerField()

    def validate(self, data):
        from books.models import Book
        from courses.models import Course

        item_type = data["item_type"]
        object_id = data["object_id"]
        user = self.context["request"].user

        if item_type == "course":
            try:
                obj = Course.objects.get(id=object_id)
            except Course.DoesNotExist:
                raise serializers.ValidationError({"object_id": "Course not found."})
            if already_owns(user, obj):
                raise serializers.ValidationError("You already own this course.")
            data["object"] = obj

            # Apply scholarship discount if the user has an approved one for this course
            from courses.models import Scholarship
            scholarship = Scholarship.objects.filter(
                user=user, course=obj, status="approved"
            ).first()
            if scholarship and scholarship.discount_percent:
                discount = scholarship.discount_percent / 100
                data["price"] = round(obj.price * (1 - discount), 2)
                data["scholarship"] = scholarship
            else:
                data["price"] = obj.price
                data["scholarship"] = None

        elif item_type == "digital_book":
            try:
                obj = Book.objects.get(id=object_id)
            except Book.DoesNotExist:
                raise serializers.ValidationError({"object_id": "Book not found."})
            if not obj.has_digital:
                raise serializers.ValidationError(
                    {"object_id": "This book has no digital format."}
                )
            if already_owns(user, obj, format="digital"):
                raise serializers.ValidationError(
                    "You already own the digital version of this book."
                )
            data["object"] = obj
            data["price"] = obj.digital_price

        return data


class ShippingAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingAddress
        fields = [
            "full_name",
            "phone",
            "address_line",
            "city",
            "country",
            "postal_code",
        ]


class CartCheckoutSerializer(serializers.Serializer):
    """For checking out physical books from cart."""

    shipping_address = ShippingAddressSerializer()


class BookSaleSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source="order.id")
    student_name = serializers.SerializerMethodField()
    student_email = serializers.ReadOnlyField(source="order.user.email")
    book_title = serializers.ReadOnlyField(source="book.title")
    type = serializers.CharField(source="item_type")
    amount = serializers.DecimalField(
        source="total_price", max_digits=10, decimal_places=2
    )
    payment_status = serializers.ReadOnlyField(source="order.status")
    payment_reference = serializers.ReadOnlyField(source="order.payment_reference")
    date = serializers.DateTimeField(source="order.created_at")
    shipping_address = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "order_id",
            "student_name",
            "student_email",
            "book_title",
            "type",
            "quantity",
            "amount",
            "payment_status",
            "payment_reference",
            "date",
            "shipping_address",
        ]

    def get_student_name(self, obj):
        user = obj.order.user
        return f"{user.first_name} {user.last_name}".strip() or user.email

    def get_shipping_address(self, obj):
        if obj.item_type != "physical_book":
            return None
        address = getattr(obj.order, "shipping_address", None)
        if not address:
            return None
        return {
            "full_name": address.full_name,
            "phone": address.phone,
            "address_line": address.address_line,
            "city": address.city,
            "country": address.country,
            "postal_code": address.postal_code,
        }
