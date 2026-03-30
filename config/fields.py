# config/fields.py
from rest_framework import serializers
from .validators import sanitize_html

class RichTextField(serializers.CharField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        return sanitize_html(value)