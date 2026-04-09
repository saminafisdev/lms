EMAIL_TEMPLATE_VARIABLES = {
    "welcome": ["first_name", "platform_url"],
    "password_reset": ["first_name", "reset_link"],
    "course_purchase": ["first_name", "course_name", "amount"],
    "book_purchase": ["first_name", "book_title", "format", "amount"],
    "blog_approved": ["first_name", "blog_title"],
    "blog_rejected": ["first_name", "blog_title", "rejection_reason"],
    "newsletter": [],
    "certificate_issued": [
        "first_name",
        "course_name",
        "certificate_id",
        "download_url",
        "verify_url",
    ],
}
