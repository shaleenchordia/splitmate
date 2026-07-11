from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """App login account. Group members may exist without an account
    (e.g. a guest on a trip); a User can claim a member by name."""
