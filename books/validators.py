import re
from django.core.exceptions import ValidationError

def validate_isbn(value):
    """
    Validates ISBN-10 or ISBN-13 format.
    """
    # Remove hyphens and spaces
    clean_isbn = re.sub(r'[- ]', '', value)
    
    if len(clean_isbn) == 10:
        if not re.match(r'^\d{9}[\dX]$', clean_isbn):
            raise ValidationError("Invalid ISBN-10 format.")
    elif len(clean_isbn) == 13:
        if not re.match(r'^\d{13}$', clean_isbn):
            raise ValidationError("Invalid ISBN-13 format.")
    else:
        raise ValidationError("ISBN must be 10 or 13 characters long (excluding hyphens).")

def validate_pdf(value):
    """
    Validates that the file is a PDF.
    """
    if not value.name.lower().endswith('.pdf'):
        raise ValidationError("Only PDF files are allowed for the book sample.")
