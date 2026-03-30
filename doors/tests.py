from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from accounts.models import User
from .models import Door

class DoorAPITests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin@example.com", password="password123", role="admin"
        )
        self.student_user = User.objects.create_user(
            email="student@example.com", password="password123", role="student"
        )
        self.door_visible = Door.objects.create(
            title="Visible Door", content="Content", is_visible=True, icon="test.png"
        )
        self.door_hidden = Door.objects.create(
            title="Hidden Door", content="Content", is_visible=False, icon="test.png"
        )
        self.url = reverse("door-list")

    def test_public_can_list_visible_only(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Results is not there since I removed pagination in views.py
        # Wait, if pagination_class = None, it's a direct list
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Visible Door")
        self.assertNotIn("is_visible", response.data[0])

    def test_admin_can_list_all_and_see_visibility(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertIn("is_visible", response.data[0])

    def test_student_cannot_create_door(self):
        self.client.force_authenticate(user=self.student_user)
        data = {"title": "New Door", "content": "Content", "icon": ""} # Empty icon for now
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_door(self):
        self.client.force_authenticate(user=self.admin_user)
        import os
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        import io

        # Create a dummy image
        img = Image.new('RGB', (100, 100), color = (73, 109, 137))
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        
        icon = SimpleUploadedFile("icon.png", img_byte_arr, content_type="image/png")
        data = {"title": "Admin Door", "content": "Content", "icon": icon, "is_visible": True}
        response = self.client.post(self.url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Door.objects.count(), 3)
