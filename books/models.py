from django.db import models
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from django_resized import ResizedImageField
from .validators import validate_isbn, validate_pdf

class BookCategory(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Book Categories"

class Book(models.Model):
    category = models.ForeignKey(
        BookCategory, on_delete=models.SET_NULL, null=True, related_name="books"
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    author = models.CharField(max_length=255)
    description = models.TextField()
    cover_image = ResizedImageField(
        size=[800, 1000],
        crop=["middle", "center"],
        quality=100,
        upload_to="books/covers/",
        force_format="WEBP",
    )
    isbn = models.CharField(
        max_length=20, unique=True, validators=[validate_isbn], help_text="10 or 13 digit ISBN"
    )
    language = models.CharField(max_length=100)
    publisher = models.CharField(max_length=255)
    published_date = models.DateField()
    number_of_pages = models.PositiveIntegerField()
    
    # Media
    sample_file = models.FileField(
        upload_to="books/samples/", validators=[validate_pdf], blank=True, null=True
    )
    video_url = models.URLField(blank=True, null=True, help_text="Link to a book trailer or intro video")
    
    # Format Availability & Pricing
    has_physical = models.BooleanField(default=False)
    physical_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    stock_count = models.PositiveIntegerField(default=0)
    
    has_digital = models.BooleanField(default=False)
    digital_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    tags = models.JSONField(default=list, blank=True, help_text="List of tags for the book")
    
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.has_physical and self.physical_price <= 0:
            raise ValidationError({"physical_price": "Physical price must be greater than 0 if physical version is available."})
        if self.has_digital and self.digital_price <= 0:
            raise ValidationError({"digital_price": "Digital price must be greater than 0 if digital version is available."})

    def __str__(self):
        return self.title

    class Meta:
        ordering = ["-created_at"]

class BookGalleryImage(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="gallery_images")
    image = ResizedImageField(
        size=[1200, 800],
        crop=["middle", "center"],
        quality=100,
        upload_to="books/gallery/",
        force_format="WEBP",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Gallery image for {self.book.title}"
