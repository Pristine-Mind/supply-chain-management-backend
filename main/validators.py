import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class CustomPasswordValidator:
    """
    Custom password validator with enhanced security requirements.
    """

    def __init__(self, min_length=12):
        self.min_length = min_length

    def validate(self, password, user=None):
        """
        Validate password against multiple security criteria.
        """
        errors = []

        # Check minimum length
        if len(password) < self.min_length:
            errors.append(
                ValidationError(
                    _("Password must be at least %(min_length)d characters long."),
                    code="password_too_short",
                    params={"min_length": self.min_length},
                )
            )

        # Check for uppercase letter
        if not re.search(r"[A-Z]", password):
            errors.append(
                ValidationError(
                    _("Password must contain at least one uppercase letter."),
                    code="password_no_uppercase",
                )
            )

        # Check for lowercase letter
        if not re.search(r"[a-z]", password):
            errors.append(
                ValidationError(
                    _("Password must contain at least one lowercase letter."),
                    code="password_no_lowercase",
                )
            )

        # Check for digit
        if not re.search(r"\d", password):
            errors.append(
                ValidationError(
                    _("Password must contain at least one digit."),
                    code="password_no_digit",
                )
            )

        # Check for special character
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append(
                ValidationError(
                    _('Password must contain at least one special character (!@#$%^&*(),.?":{}|<>).'),
                    code="password_no_special",
                )
            )

        # Check for common patterns
        common_patterns = [
            r"(.)\1{2,}",  # Three or more consecutive identical characters
            r"123456",  # Sequential numbers
            r"abcdef",  # Sequential letters
            r"qwerty",  # Keyboard patterns
            r"password",  # Common word
            r"admin",  # Common word
        ]

        for pattern in common_patterns:
            if re.search(pattern, password.lower()):
                errors.append(
                    ValidationError(
                        _("Password contains common patterns that are easy to guess."),
                        code="password_common_pattern",
                    )
                )
                break

        # Check against user information if provided
        if user:
            user_info = [
                user.username.lower(),
                user.first_name.lower(),
                user.last_name.lower(),
                user.email.lower().split("@")[0],
            ]

            for info in user_info:
                if info and len(info) >= 3 and info in password.lower():
                    errors.append(
                        ValidationError(
                            _("Password cannot contain your personal information."),
                            code="password_contains_user_info",
                        )
                    )
                    break

        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return _(
            "Your password must be at least %(min_length)d characters long, "
            "contain uppercase and lowercase letters, at least one digit, "
            "one special character, and cannot contain common patterns or "
            "your personal information."
        ) % {"min_length": self.min_length}


class PasswordHistoryValidator:
    """
    Validator to prevent password reuse.
    """

    def __init__(self, password_history_count=5):
        self.password_history_count = password_history_count

    def validate(self, password, user=None):
        """
        Check if password was used recently.
        """
        if user and hasattr(user, "password_history"):
            # This would require implementing a PasswordHistory model
            # For now, we'll just check against current password
            from django.contrib.auth.hashers import check_password

            if check_password(password, user.password):
                raise ValidationError(
                    _("You cannot reuse your current password."),
                    code="password_reused",
                )

    def get_help_text(self):
        return _("You cannot reuse any of your last %(count)d passwords.") % {"count": self.password_history_count}


class PasswordExpiryValidator:
    """
    Validator to enforce password expiry.
    """

    def __init__(self, max_age_days=90):
        self.max_age_days = max_age_days

    def validate(self, password, user=None):
        """
        Check if password needs to be changed due to age.
        This is mainly for informational purposes during login.
        """
        # This would be checked during login, not during password creation
        pass

    def get_help_text(self):
        return _("Passwords expire after %(days)d days.") % {"days": self.max_age_days}
