from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager["User"]):
    """
    Кастомный менеджер для модели пользователя (Паттерн: Factory Method).
    """

    def create_user(
        self, email: str, password: str | None = None, **extra_fields: dict
    ) -> "User":
        if not email:
            raise ValueError(_("Email is required"))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, email: str, password: str | None = None, **extra_fields: dict
    ) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Кастомная модель пользователя портала.
    """

    class Role(models.TextChoices):
        MANAGER = "MANAGER", _("Менеджер")
        STOREKEEPER = "STOREKEEPER", _("Кладовщик")
        CLIENT = "CLIENT", _("Клиент (B2B)")
        ADMIN = "ADMIN", _("Администратор")

    username = None

    email = models.EmailField(_("email address"), unique=True)

    role = models.CharField(_("Роль"), max_length=20, choices=Role.choices, default=Role.CLIENT)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    manager = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subordinates",
        verbose_name="Руководитель",
    )

    def __str__(self) -> str:
        return f"{self.email} - {self.get_role_display()}"