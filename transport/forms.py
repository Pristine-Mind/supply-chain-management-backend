# transport/forms.py
from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import (
    Delivery,
    DeliveryPriority,
    DeliveryRating,
    DeliveryTracking,
    Transporter,
    TransportStatus,
    VehicleType,
)


class TransporterForm(forms.ModelForm):
    """Form for creating/updating transporter profiles"""

    class Meta:
        model = Transporter
        fields = [
            "license_number",
            "phone",
            "vehicle_type",
            "vehicle_number",
            "vehicle_capacity",
            "current_latitude",
            "current_longitude",
            "is_available",
        ]
        widgets = {
            "license_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter license number"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "+1234567890"}),
            "vehicle_type": forms.Select(attrs={"class": "form-control"}),
            "vehicle_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter vehicle number"}),
            "vehicle_capacity": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Capacity in kg", "step": "0.01"}
            ),
            "current_latitude": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Latitude", "step": "0.000001"}
            ),
            "current_longitude": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Longitude", "step": "0.000001"}
            ),
            "is_available": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_license_number(self):
        license_number = self.cleaned_data.get("license_number")
        if license_number:
            # Check if license number already exists (excluding current instance)
            queryset = Transporter.objects.filter(license_number=license_number)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                raise ValidationError("A transporter with this license number already exists.")

        return license_number

    def clean_vehicle_capacity(self):
        capacity = self.cleaned_data.get("vehicle_capacity")
        if capacity and capacity <= 0:
            raise ValidationError("Vehicle capacity must be greater than 0.")
        return capacity


class DeliveryForm(forms.ModelForm):
    """Form for creating/updating deliveries"""

    class Meta:
        model = Delivery
        fields = [
            "marketplace_sale",
            "pickup_address",
            "pickup_latitude",
            "pickup_longitude",
            "pickup_contact_name",
            "pickup_contact_phone",
            "delivery_address",
            "delivery_latitude",
            "delivery_longitude",
            "delivery_contact_name",
            "delivery_contact_phone",
            "package_weight",
            "package_dimensions",
            "special_instructions",
            "priority",
            "requested_pickup_date",
            "requested_delivery_date",
            "delivery_fee",
            "distance_km",
        ]
        widgets = {
            "marketplace_sale": forms.Select(attrs={"class": "form-control"}),
            "pickup_address": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Enter pickup address"}
            ),
            "pickup_latitude": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
            "pickup_longitude": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
            "pickup_contact_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Contact person name"}),
            "pickup_contact_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "+1234567890"}),
            "delivery_address": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Enter delivery address"}
            ),
            "delivery_latitude": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
            "delivery_longitude": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
            "delivery_contact_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Contact person name"}),
            "delivery_contact_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "+1234567890"}),
            "package_weight": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "placeholder": "Weight in kg"}
            ),
            "package_dimensions": forms.TextInput(attrs={"class": "form-control", "placeholder": "L x W x H in cm"}),
            "special_instructions": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Any special handling instructions"}
            ),
            "priority": forms.Select(attrs={"class": "form-control"}),
            "requested_pickup_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "requested_delivery_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "delivery_fee": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "placeholder": "Delivery fee"}
            ),
            "distance_km": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "placeholder": "Distance in km"}
            ),
        }

    def clean_package_weight(self):
        weight = self.cleaned_data.get("package_weight")
        if weight and weight <= 0:
            raise ValidationError("Package weight must be greater than 0.")
        return weight

    def clean_delivery_fee(self):
        fee = self.cleaned_data.get("delivery_fee")
        if fee and fee < 0:
            raise ValidationError("Delivery fee cannot be negative.")
        return fee

    def clean(self):
        cleaned_data = super().clean()
        pickup_date = cleaned_data.get("requested_pickup_date")
        delivery_date = cleaned_data.get("requested_delivery_date")

        if pickup_date and delivery_date:
            if delivery_date <= pickup_date:
                raise ValidationError("Delivery date must be after pickup date.")

        return cleaned_data


class DeliveryAssignmentForm(forms.Form):
    """Form for assigning deliveries to transporters"""

    transporter = forms.ModelChoiceField(
        queryset=Transporter.objects.filter(is_available=True, is_verified=True),
        widget=forms.Select(attrs={"class": "form-control"}),
        empty_label="Select a transporter",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Assignment notes (optional)"}),
    )

    def __init__(self, *args, **kwargs):
        delivery = kwargs.pop("delivery", None)
        super().__init__(*args, **kwargs)

        if delivery:
            # Filter transporters by vehicle capacity
            self.fields["transporter"].queryset = Transporter.objects.filter(
                is_available=True, is_verified=True, vehicle_capacity__gte=delivery.package_weight
            )


class DeliveryTrackingForm(forms.ModelForm):
    """Form for adding delivery tracking updates"""

    class Meta:
        model = DeliveryTracking
        fields = ["status", "latitude", "longitude", "notes"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-control"}),
            "latitude": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.000001", "placeholder": "Latitude (optional)"}
            ),
            "longitude": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.000001", "placeholder": "Longitude (optional)"}
            ),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Status update notes"}),
        }


class DeliveryRatingForm(forms.ModelForm):
    """Form for rating deliveries"""

    class Meta:
        model = DeliveryRating
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.RadioSelect(
                choices=[
                    (5, "5 - Excellent"),
                    (4, "4 - Good"),
                    (3, "3 - Average"),
                    (2, "2 - Poor"),
                    (1, "1 - Very Poor"),
                ]
            ),
            "comment": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "placeholder": "Share your experience (optional)"}
            ),
        }


class DeliveryFilterForm(forms.Form):
    """Form for filtering deliveries"""

    status = forms.ChoiceField(
        choices=[("", "All Statuses")] + list(TransportStatus.choices),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    priority = forms.ChoiceField(
        choices=[("", "All Priorities")] + list(DeliveryPriority.choices),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    transporter = forms.ModelChoiceField(
        queryset=Transporter.objects.all(),
        required=False,
        empty_label="All Transporters",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    weight_max = forms.DecimalField(
        required=False,
        max_digits=8,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Max weight (kg)", "step": "0.01"}),
    )
    distance_max = forms.DecimalField(
        required=False,
        max_digits=8,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Max distance (km)", "step": "0.01"}),
    )
    pickup_date_from = forms.DateTimeField(
        required=False, widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"})
    )
    pickup_date_to = forms.DateTimeField(
        required=False, widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"})
    )


class TransporterRegistrationForm(forms.ModelForm):
    """Form for transporter registration with user details"""

    first_name = forms.CharField(
        max_length=30, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "First Name"})
    )
    last_name = forms.CharField(
        max_length=30, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Last Name"})
    )
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email Address"}))
    username = forms.CharField(
        max_length=150, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Username"})
    )
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Password"}))
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirm Password"})
    )

    class Meta:
        model = Transporter
        fields = ["license_number", "phone", "vehicle_type", "vehicle_number", "vehicle_capacity"]
        widgets = {
            "license_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "License Number"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Phone Number"}),
            "vehicle_type": forms.Select(attrs={"class": "form-control"}),
            "vehicle_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Vehicle Number"}),
            "vehicle_capacity": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Vehicle Capacity (kg)", "step": "0.01"}
            ),
        }

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise ValidationError("Passwords don't match")

        return password2

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if User.objects.filter(username=username).exists():
            raise ValidationError("Username already exists")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise ValidationError("Email already registered")
        return email

    def save(self, commit=True):
        # Create user first
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
        )

        # Create transporter profile
        transporter = super().save(commit=False)
        transporter.user = user

        if commit:
            transporter.save()

        return transporter


class BulkDeliveryActionForm(forms.Form):
    """Form for bulk actions on deliveries"""

    action = forms.ChoiceField(
        choices=[
            ("assign", "Assign to Transporter"),
            ("priority_high", "Set Priority to High"),
            ("priority_urgent", "Set Priority to Urgent"),
            ("cancel", "Cancel Deliveries"),
            ("export", "Export Selected"),
        ],
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    transporter = forms.ModelChoiceField(
        queryset=Transporter.objects.filter(is_available=True, is_verified=True),
        required=False,
        empty_label="Select Transporter",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get("action")
        transporter = cleaned_data.get("transporter")

        if action == "assign" and not transporter:
            raise ValidationError("Transporter is required for assignment action.")

        return cleaned_data
