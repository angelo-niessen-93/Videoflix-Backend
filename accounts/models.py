from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    username = models.CharField(max_length=254, unique=True)
    email = models.EmailField(unique=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("email"), name="user_email_ci_unique"
            )
        ]


class EmailJob(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=16)
    token = models.TextField()
    status = models.CharField(max_length=16, default="pending", db_index=True)
    error = models.CharField(max_length=128, blank=True)
    job_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
