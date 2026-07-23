"""Admin forms for the custom User.

Django's built-in UserCreationForm / UserChangeForm assume a ``username`` field,
so a custom email-keyed user needs these thin subclasses pointed at our model.
"""

from django.contrib.auth.forms import BaseUserCreationForm
from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm

from .models import User


class UserCreationForm(BaseUserCreationForm):
    """Add-user form in the admin. BaseUserCreationForm supplies password1/2."""

    class Meta:
        model = User
        fields = ("email",)


class UserChangeForm(DjangoUserChangeForm):
    """Edit-user form. Inherits the read-only hashed-password widget."""

    class Meta:
        model = User
        fields = "__all__"
