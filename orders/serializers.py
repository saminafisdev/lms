from rest_framework import serializers

from books.serializers import PublicBookSerializer
from courses.serializers import SimpleCourseSerializer

from .models import Cart, CartItem, Order, OrderItem, ShippingAddress
from .utils import already_owns


class CartItemReadSerializer(serializers.ModelSerializer):
    """Read-only representation of a cart item with type-specific detail."""

    display_name = serializers.SerializerMethodField()
    unit_price = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()
    item_detail = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            "id",
            "item_type",
            "display_name",
            "unit_price",
            "quantity",
            "total_price",
            "item_detail",
            "added_at",
        ]

    def get_display_name(self, obj):
        return obj.get_display_name()

    def get_unit_price(self, obj):
        return obj.get_unit_price()

    def get_total_price(self, obj):
        return obj.get_total_price()

    def get_item_detail(self, obj):
        request = self.context.get("request")
        if obj.item_type == CartItem.ItemType.COURSE:
            return SimpleCourseSerializer(obj.course, context={"request": request}).data
        elif obj.item_type == CartItem.ItemType.BUNDLE:
            from courses.serializers import BundleSerializer
            return BundleSerializer(obj.bundle, context={"request": request}).data
        else:
            return PublicBookSerializer(obj.book, context={"request": request}).data


class AddToCartSerializer(serializers.Serializer):
    """Write serializer for adding an item to the cart."""

    ITEM_TYPE_CHOICES = CartItem.ItemType.choices
    item_type = serializers.ChoiceField(choices=ITEM_TYPE_CHOICES)
    object_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate(self, data):
        from books.models import Book
        from courses.models import Bundle, Course

        item_type = data["item_type"]
        object_id = data["object_id"]
        quantity = data.get("quantity", 1)
        user = self.context["request"].user

        if item_type == CartItem.ItemType.COURSE:
            try:
                obj = Course.objects.get(id=object_id)
            except Course.DoesNotExist:
                raise serializers.ValidationError({"object_id": "Course not found."})
            if already_owns(user, obj):
                raise serializers.ValidationError("You already own this course.")
            data["object"] = obj
            data["quantity"] = 1

        elif item_type == CartItem.ItemType.BUNDLE:
            try:
                obj = Bundle.objects.prefetch_related("courses").get(
                    id=object_id, is_active=True
                )
            except Bundle.DoesNotExist:
                raise serializers.ValidationError(
                    {"object_id": "Bundle not found or inactive."}
                )
            owned = [c for c in obj.courses.all() if already_owns(user, c)]
            if len(owned) == obj.courses.count():
                raise serializers.ValidationError(
                    "You already own all courses in this bundle."
                )
            data["object"] = obj
            data["quantity"] = 1

        elif item_type == CartItem.ItemType.DIGITAL_BOOK:
            try:
                obj = Book.objects.get(id=object_id)
            except Book.DoesNotExist:
                raise serializers.ValidationError({"object_id": "Book not found."})
            if not obj.has_digital:
                raise serializers.ValidationError(
                    {"object_id": "This book is not available in digital format."}
                )
            if already_owns(user, obj, format="digital"):
                raise serializers.ValidationError(
                    "You already own the digital version of this book."
                )
            data["object"] = obj
            data["quantity"] = 1

        elif item_type == CartItem.ItemType.PHYSICAL_BOOK:
            try:
                obj = Book.objects.get(id=object_id)
            except Book.DoesNotExist:
                raise serializers.ValidationError({"object_id": "Book not found."})
            if not obj.has_physical:
                raise serializers.ValidationError(
                    {"object_id": "This book is not available in physical format."}
                )
            if obj.stock_count <= 0:
                raise serializers.ValidationError({"object_id": "This book is out of stock."})
            if already_owns(user, obj, format="physical"):
                raise serializers.ValidationError(
                    "You already own the physical version of this book."
                )
            if quantity > obj.stock_count:
                raise serializers.ValidationError(
                    {"quantity": f"Only {obj.stock_count} copies available."}
                )
            data["object"] = obj

        return data


# Keep CartItemSerializer as an alias for backward compat (used in a few places)
CartItemSerializer = CartItemReadSerializer


class CartSerializer(serializers.ModelSerializer):
    items = CartItemReadSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()
    has_physical_items = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "items", "total", "has_physical_items", "updated_at"]

    def get_total(self, obj):
        return obj.get_total()

    def get_has_physical_items(self, obj):
        return obj.has_physical_items()


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
    shipping_address = ShippingAddressSerializer(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_type",
            "status",
            "fulfillment_status",
            "total_amount",
            "items",
            "shipping_address",
            "created_at",
        ]
        read_only_fields = fields


class UpdateFulfillmentSerializer(serializers.Serializer):
    fulfillment_status = serializers.ChoiceField(
        choices=[
            Order.FulfillmentStatus.PROCESSING,
            Order.FulfillmentStatus.SHIPPED,
            Order.FulfillmentStatus.DELIVERED,
            Order.FulfillmentStatus.CANCELLED,
        ]
    )


class DirectPurchaseSerializer(serializers.Serializer):
    """For buying a course, bundle, or digital book directly."""

    ITEM_TYPE_CHOICES = (
        ("course", "Course"),
        ("bundle", "Bundle"),
        ("digital_book", "Digital Book"),
    )
    item_type = serializers.ChoiceField(choices=ITEM_TYPE_CHOICES)
    object_id = serializers.IntegerField()

    def validate(self, data):
        from books.models import Book
        from courses.models import Bundle, Course

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

        elif item_type == "bundle":
            try:
                obj = Bundle.objects.prefetch_related("courses").get(
                    id=object_id, is_active=True
                )
            except Bundle.DoesNotExist:
                raise serializers.ValidationError(
                    {"object_id": "Bundle not found or inactive."}
                )
            already_owned = [c for c in obj.courses.all() if already_owns(user, c)]
            if len(already_owned) == obj.courses.count():
                raise serializers.ValidationError(
                    "You already own all courses in this bundle."
                )
            data["object"] = obj
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
            data["scholarship"] = None

        return data


class CartCheckoutSerializer(serializers.Serializer):
    """For checking out the cart. shipping_address required only when cart has physical items."""

    shipping_address = ShippingAddressSerializer(required=False)


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
