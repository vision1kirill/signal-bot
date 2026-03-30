"""
Django management command: создаёт суперпользователя если его нет.
Использование: python manage.py ensure_superuser
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Создаёт суперпользователя если ни одного нет"

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "Admin12345!")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@admin.com")

        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username=username, email=email, password=password)
            self.stdout.write(self.style.SUCCESS(f"Суперпользователь '{username}' создан."))
        else:
            self.stdout.write(f"Суперпользователь '{username}' уже существует.")
