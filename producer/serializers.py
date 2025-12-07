import json
from datetime import datetime

from django.contrib.gis.geos import Point
from rest_framework import serializers

from user.models import UserProfile

from .models import (
    AuditLog,
    B2BPriceTier,
    Brand,
    Category,
    City,
    Customer,
    DirectSale,
    LedgerEntry,
    MarketplaceBulkPriceTier,
    MarketplaceProduct,
    MarketplaceProductReview,
    MarketplaceProductVariant,
    Order,
    Payment,
    Producer,
    Product,
    ProductImage,
    PurchaseOrder,
    Sale,
    StockList,
    Subcategory,
    SubSubcategory,
)


class ProducerSerializer(serializers.ModelSerializer):
    location_details = serializers.SerializerMethodField()

    class Meta:
        model = Producer
        fields = "__all__"
        extra_kwargs = {"user": {"read_only": True}}

    def get_location_details(self, producer) -> dict:
        if producer and producer.location:
            return json.loads(producer.location.geojson)
        return None

    def validate_registration_number(self, value):
        """
        Validate that the registration number is alphanumeric and unique.
        """
        if not value.isalnum():
            raise serializers.ValidationError("Registration number must be alphanumeric.")
        return value


class CategorySerializer(serializers.ModelSerializer):
    subcategories_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "code", "name", "description", "is_active", "created_at", "updated_at", "subcategories_count"]
        read_only_fields = ["created_at", "updated_at"]

    def get_subcategories_count(self, obj):
        return obj.subcategories.filter(is_active=True).count()


class SubSubcategorySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="subcategory.category.name", read_only=True)
    category_code = serializers.CharField(source="subcategory.category.code", read_only=True)
    subcategory_name = serializers.CharField(source="subcategory.name", read_only=True)

    class Meta:
        model = SubSubcategory
        fields = [
            "id",
            "code",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
            "subcategory",
            "category_name",
            "category_code",
            "subcategory_name",
        ]
        read_only_fields = ["created_at", "updated_at"]


# Light version for Product serialization - no nested objects
class SubSubcategoryLightSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="subcategory.category.name", read_only=True)
    category_code = serializers.CharField(source="subcategory.category.code", read_only=True)
    subcategory_name = serializers.CharField(source="subcategory.name", read_only=True)

    class Meta:
        model = SubSubcategory
        fields = ["id", "code", "name", "category_name", "category_code", "subcategory_name"]


class SubcategoryLightSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_code = serializers.CharField(source="category.code", read_only=True)
    sub_subcategories_count = serializers.SerializerMethodField()

    class Meta:
        model = Subcategory
        fields = ["id", "code", "name", "category", "category_name", "category_code", "sub_subcategories_count"]

    def get_sub_subcategories_count(self, obj):
        return obj.sub_subcategories.filter(is_active=True).count()


class SubcategorySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_code = serializers.CharField(source="category.code", read_only=True)
    sub_subcategories = SubSubcategorySerializer(many=True, read_only=True)
    sub_subcategories_count = serializers.SerializerMethodField()

    class Meta:
        model = Subcategory
        fields = [
            "id",
            "code",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
            "category",
            "category_name",
            "category_code",
            "sub_subcategories",
            "sub_subcategories_count",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_sub_subcategories_count(self, obj):
        return obj.sub_subcategories.filter(is_active=True).count()


class CategoryHierarchySerializer(serializers.ModelSerializer):
    """Serializer for complete category hierarchy"""

    subcategories = SubcategorySerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ["id", "code", "name", "description", "is_active", "subcategories"]


class BrandSerializer(serializers.ModelSerializer):
    """Serializer for Brand model"""

    logo_url = serializers.SerializerMethodField()
    products_count = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = [
            "id",
            "name",
            "description",
            "logo",
            "logo_url",
            "website",
            "country_of_origin",
            "is_active",
            "is_verified",
            "created_at",
            "updated_at",
            "manufacturer_info",
            "contact_email",
            "contact_phone",
            "products_count",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_logo_url(self, obj):
        """Get full URL for brand logo"""
        request = self.context.get("request")
        if obj.logo and request:
            try:
                return request.build_absolute_uri(obj.logo.url)
            except Exception:
                return obj.logo.url if obj.logo else None
        return None

    def get_products_count(self, obj):
        """Get total count of products for this brand"""
        return obj.products.filter(is_active=True).count()

    def validate_name(self, value):
        """Validate brand name is unique"""
        if Brand.objects.filter(name__iexact=value).exists():
            if not self.instance or self.instance.name.lower() != value.lower():
                raise serializers.ValidationError("A brand with this name already exists.")
        return value


class BrandLightSerializer(serializers.ModelSerializer):
    """Light version of Brand serializer for nested usage"""

    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = ["id", "name", "logo_url", "is_verified", "country_of_origin"]

    def get_logo_url(self, obj):
        """Get full URL for brand logo"""
        request = self.context.get("request")
        if obj.logo and request:
            try:
                return request.build_absolute_uri(obj.logo.url)
            except Exception:
                return obj.logo.url if obj.logo else None
        return None


class ProducerCreateUpdateSerializer(serializers.ModelSerializer):
    location_details = serializers.SerializerMethodField()

    class Meta:
        model = Producer
        fields = "__all__"
        extra_kwargs = {"user": {"read_only": True}}

    def get_location_details(self, producer) -> dict:
        if producer and producer.location:
            return json.loads(producer.location.geojson)
        return None

    def validate_registration_number(self, value):
        """
        Validate that the registration number is alphanumeric and unique.
        """
        if not value.isalnum():
            raise serializers.ValidationError("Registration number must be alphanumeric.")
        return value

    def create(self, validated_data):
        location_data = self.initial_data.get("location")
        if location_data:
            latitude = location_data.get("latitude")
            longitude = location_data.get("longitude")

            if latitude is not None and longitude is not None:
                validated_data["location"] = Point(longitude, latitude)
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        location_data = self.initial_data.get("location")
        if location_data:
            latitude = location_data.get("latitude")
            longitude = location_data.get("longitude")

            if latitude is not None and longitude is not None:
                validated_data["location"] = Point(longitude, latitude)
        validated_data["user"] = self.context["request"].user
        return super().update(instance, validated_data)


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = "__all__"
        extra_kwargs = {"user": {"read_only": True}}

    def validate_credit_limit(self, value):
        """
        Ensure the credit limit is a non-negative value.
        """
        if value < 0:
            raise serializers.ValidationError("Credit limit cannot be negative.")
        return value

    def validate_current_balance(self, value):
        """
        Ensure the current balance is non-negative.
        """
        if value < 0:
            raise serializers.ValidationError("Current balance cannot be negative.")
        return value

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().update(instance, validated_data)


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "created_at"]

    def get_image(self, obj):
        request = self.context.get("request") if hasattr(self, "context") else None
        if obj.image:
            try:
                # Prefer absolute URL if request is available
                return request.build_absolute_uri(obj.image.url) if request else obj.image.url
            except Exception:
                return obj.image.url
        return None


class ProductStockUpdateSerializer(serializers.Serializer):
    stock = serializers.IntegerField(min_value=0)


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    uploaded_images = serializers.ListField(child=serializers.ImageField(), write_only=True, required=False)
    category_details = serializers.CharField(source="get_old_category_display", read_only=True)
    deleted_images = serializers.ListField(child=serializers.IntegerField(), write_only=True, required=False)

    # New category hierarchy fields - using light serializers for better performance
    category_info = CategorySerializer(source="category", read_only=True)
    subcategory_info = SubcategoryLightSerializer(source="subcategory", read_only=True)
    sub_subcategory_info = SubSubcategoryLightSerializer(source="sub_subcategory", read_only=True)

    # Brand information
    brand_info = BrandLightSerializer(source="brand", read_only=True)
    brand_name = serializers.CharField(source="get_brand_name", read_only=True)
    brand_details = serializers.SerializerMethodField()

    # Choice field display methods
    size_display = serializers.CharField(source="get_size_display", read_only=True)
    color_display = serializers.CharField(source="get_color_display", read_only=True)

    class Meta:
        model = Product
        fields = "__all__"
        extra_kwargs = {"user": {"read_only": True}}

    def get_brand_details(self, obj):
        """Get brand information from the brand_info property"""
        return obj.brand_info

    def validate_price(self, value):
        """
        Ensure that the product price is a positive number.
        """
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than zero.")
        return value

    def validate_cost_price(self, value):
        """
        Ensure that the cost price is a positive number and not greater than the selling price.
        """
        if value <= 0:
            raise serializers.ValidationError("Cost price must be greater than zero.")
        return value

    def validate_size(self, value):
        """
        Validate size choice if provided
        """
        if value and value not in [choice[0] for choice in Product.SizeChoices.choices]:
            raise serializers.ValidationError(
                f"Invalid size choice. Must be one of: {[choice[0] for choice in Product.SizeChoices.choices]}"
            )
        return value

    def validate_color(self, value):
        """
        Validate color choice if provided
        """
        if value and value not in [choice[0] for choice in Product.ColorChoices.choices]:
            raise serializers.ValidationError(
                f"Invalid color choice. Must be one of: {[choice[0] for choice in Product.ColorChoices.choices]}"
            )
        return value

    # def validate(self, data):
    #     """
    #     Ensure that the cost price is not greater than the selling price.
    #     """
    #     if data["cost_price"] > data["price"]:
    #         raise serializers.ValidationError("Cost price cannot be greater than selling price.")
    #     return data

    def create(self, validated_data):
        uploaded_images = validated_data.pop("uploaded_images", [])
        validated_data["user"] = self.context["request"].user
        product = super().create(validated_data)
        for image in uploaded_images:
            ProductImage.objects.create(product=product, image=image)

        return product

    def update(self, instance, validated_data):
        uploaded_images = validated_data.pop("uploaded_images", [])
        deleted_images = validated_data.pop("deleted_images", [])
        validated_data["user"] = self.context["request"].user
        product = super().update(instance, validated_data)
        for image in uploaded_images:
            ProductImage.objects.create(product=product, image=image)

        if deleted_images:
            ProductImage.objects.filter(id__in=deleted_images, product=product).delete()

        return product


class OrderSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)
    customer_details = CustomerSerializer(source="customer", read_only=True)
    product_details = ProductSerializer(source="product", read_only=True)
    order_number = serializers.CharField(read_only=True)

    class Meta:
        model = Order
        fields = "__all__"
        extra_kwargs = {"user": {"read_only": True}}

    def validate_quantity(self, value):
        """
        Ensure the order quantity is a positive integer.
        """
        if value <= 0:
            raise serializers.ValidationError("Order quantity must be greater than zero.")
        return value

    def validate_total_price(self, value):
        """
        Ensure that the total price is positive.
        """
        if value <= 0:
            raise serializers.ValidationError("Total price must be greater than zero.")
        return value

    def validate_status(self, value):
        """
        Ensure the status is one of the defined choices.
        """
        if value not in dict(Order.Status.choices).keys():
            raise serializers.ValidationError("Invalid status choice.")
        return value

    # def validate_delivery_date(self, value):
    #     """
    #     Ensure the delivery date is not in the past or before the order date.
    #     """
    #     if value and value < datetime.now():
    #         raise serializers.ValidationError("Delivery date cannot be in the past.")
    #     return value

    def validate(self, data):
        # Ensure delivery_date is after order_date
        if "delivery_date" in data and data["delivery_date"] and data["delivery_date"] < data["order_date"]:
            raise serializers.ValidationError("Delivery date cannot be before the order date.")

        # Ensure payment_due_date is after order_date
        if "payment_due_date" in data and data["payment_due_date"] and data["payment_due_date"] < data["order_date"]:
            raise serializers.ValidationError("Payment due date cannot be before the order date.")

        return data

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().update(instance, validated_data)


class SaleSerializer(serializers.ModelSerializer):
    order_details = OrderSerializer(source="order", read_only=True)
    payment_status_display = serializers.CharField(source="get_payment_status_display", read_only=True)

    class Meta:
        model = Sale
        fields = "__all__"
        extra_kwargs = {"user": {"read_only": True}}

    def validate_quantity(self, value):
        """
        Ensure the sale quantity is a positive integer.
        """
        if value <= 0:
            raise serializers.ValidationError("Sale quantity must be greater than zero.")
        return value

    def validate_sale_price(self, value):
        """
        Ensure the sale price is a positive number.
        """
        if value <= 0:
            raise serializers.ValidationError("Sale price must be greater than zero.")
        return value

    def validate(self, data):
        """
        Ensure that the sale price does not exceed the original product price.
        """
        # product = data["order"]
        # if data["sale_price"] > product.product.price:
        #     raise serializers.ValidationError("Sale price cannot be greater than the original product price.")
        return data

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().update(instance, validated_data)


class CustomerSalesSerializer(serializers.Serializer):
    total_sales = serializers.FloatField()
    name = serializers.CharField()
    id = serializers.IntegerField()

    class Meta:
        fields = ["id", "name", "total_sales"]


class CustomerOrdersSerializer(serializers.ModelSerializer):
    total_orders = serializers.IntegerField()

    class Meta:
        model = Customer
        fields = ["id", "name", "total_orders"]


class StockHistorySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    user_username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = StockList
        fields = ["product", "moved_date", "id", "is_pushed_to_marketplace", "product_name", "user_username"]


class StockListSerializer(serializers.ModelSerializer):
    product_details = ProductSerializer(source="product", read_only=True)
    user_username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = StockList
        fields = [
            "id",
            "product",
            "product_details",
            "moved_date",
            "is_pushed_to_marketplace",
            "user",
            "user_username",
        ]


class MarketplaceBulkPriceTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketplaceBulkPriceTier
        fields = ["min_quantity", "discount_percent", "price_per_unit"]


class B2BPriceTierSerializer(serializers.ModelSerializer):
    customer_type_display = serializers.CharField(source="get_customer_type_display", read_only=True)

    class Meta:
        model = B2BPriceTier
        fields = [
            "id",
            "customer_type",
            "customer_type_display",
            "min_quantity",
            "price_per_unit",
            "discount_percentage",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "customer_type_display"]


class MarketplaceProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketplaceProductVariant
        fields = ["name", "value", "additional_price", "stock"]


class MarketplaceProductReviewSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    user_id = serializers.IntegerField(read_only=True, source="user.id")
    username = serializers.CharField(read_only=True, source="user.username")

    class Meta:
        model = MarketplaceProductReview
        fields = ["id", "product", "user", "user_id", "username", "rating", "review_text", "created_at"]
        read_only_fields = ["id", "user", "user_id", "username", "created_at"]

    def validate_rating(self, value):
        """Validate that rating is between 1 and 5."""
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate(self, data):
        """Validate that user hasn't already reviewed this product."""
        request = self.context.get("request")
        if request and request.user:
            product = data.get("product")
            if product and MarketplaceProductReview.objects.filter(product=product, user=request.user).exists():
                raise serializers.ValidationError("You have already reviewed this product.")
        return data


class MarketplaceProductSerializer(serializers.ModelSerializer):
    product_details = ProductSerializer(source="product", read_only=True)
    latitude = serializers.FloatField(source="product.user.user_profile.latitude", read_only=True)
    longitude = serializers.FloatField(source="product.user.user_profile.longitude", read_only=True)
    min_order = serializers.IntegerField(required=False, allow_null=True)
    bulk_price_tiers = MarketplaceBulkPriceTierSerializer(many=True, read_only=True)
    b2b_price_tiers = serializers.SerializerMethodField()
    variants = MarketplaceProductVariantSerializer(many=True, read_only=True)
    reviews = MarketplaceProductReviewSerializer(many=True, read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    ratings_breakdown = serializers.SerializerMethodField()
    total_reviews = serializers.IntegerField(read_only=True)
    percent_off = serializers.FloatField(read_only=True)
    savings_amount = serializers.FloatField(read_only=True)
    is_offer_active = serializers.BooleanField(read_only=True)
    offer_countdown = serializers.SerializerMethodField()
    is_free_shipping = serializers.BooleanField(read_only=True)
    is_featured = serializers.BooleanField(read_only=False)
    is_made_in_nepal = serializers.BooleanField(read_only=False)

    # B2B Fields
    effective_price = serializers.SerializerMethodField()
    is_b2b_eligible = serializers.SerializerMethodField()

    # Brand information from product
    brand_name = serializers.CharField(read_only=True)
    brand_info = serializers.SerializerMethodField()
    is_branded_product = serializers.BooleanField(read_only=True)

    # Choice field display methods
    size_display = serializers.CharField(source="get_size_display", read_only=True)
    color_display = serializers.CharField(source="get_color_display", read_only=True)

    # Inherited values from product
    effective_size = serializers.SerializerMethodField()
    effective_color = serializers.SerializerMethodField()
    effective_additional_information = serializers.SerializerMethodField()

    class Meta:
        model = MarketplaceProduct
        fields = [
            "id",
            "product",
            "product_details",
            "discounted_price",
            "listed_price",
            "percent_off",
            "savings_amount",
            "offer_start",
            "offer_end",
            "is_offer_active",
            "offer_countdown",
            "estimated_delivery_days",
            "shipping_cost",
            "is_free_shipping",
            "is_featured",
            "is_made_in_nepal",
            "recent_purchases_count",
            "listed_date",
            "is_available",
            "min_order",
            "latitude",
            "longitude",
            "bulk_price_tiers",
            "b2b_price_tiers",
            "enable_b2b_sales",
            "b2b_price",
            "b2b_min_quantity",
            "effective_price",
            "is_b2b_eligible",
            "variants",
            "reviews",
            "average_rating",
            "ratings_breakdown",
            "total_reviews",
            "view_count",
            "rank_score",
            "size",
            "color",
            "additional_information",
            "size_display",
            "color_display",
            "effective_size",
            "effective_color",
            "effective_additional_information",
            "brand_name",
            "brand_info",
            "is_branded_product",
        ]

    def get_b2b_price_tiers(self, obj):
        """Get B2B price tiers for eligible users"""
        user = self.context.get("request", {}).user if self.context.get("request") else None
        if user and user.is_authenticated:
            try:
                profile = getattr(user, "user_profile", None)
                if profile and getattr(profile, "is_b2b_eligible", False):
                    tiers = obj.b2b_price_tiers.filter(customer_type=profile.business_type, is_active=True)
                    return B2BPriceTierSerializer(tiers, many=True).data
            except (AttributeError, TypeError):
                pass
        return []

    def get_effective_price(self, obj):
        """Get effective price for the current user"""
        user = self.context.get("request", {}).user if self.context.get("request") else None
        quantity = self.context.get("quantity", 1)
        try:
            return float(obj.get_effective_price_for_user(user, quantity))
        except (AttributeError, TypeError):
            return float(obj.price)

    def get_is_b2b_eligible(self, obj):
        """Check if current user is eligible for B2B pricing"""
        return obj.enable_b2b_sales

    def get_brand_info(self, obj):
        """Get brand information from the associated product"""
        return obj.brand_info

    def get_effective_size(self, obj):
        """Return marketplace size or inherited product size"""
        return obj.size or (obj.product.size if obj.product else None)

    def get_effective_color(self, obj):
        """Return marketplace color or inherited product color"""
        return obj.color or (obj.product.color if obj.product else None)

    def get_effective_additional_information(self, obj):
        """Return marketplace additional_information or inherited product additional_information"""
        return obj.additional_information or (obj.product.additional_information if obj.product else None)

    def get_ratings_breakdown(self, obj):
        return obj.ratings_breakdown

    def get_offer_countdown(self, obj):
        return obj.offer_countdown

    def validate_size(self, value):
        """
        Validate size choice if provided
        """
        if value and value not in [choice[0] for choice in MarketplaceProduct.SizeChoices.choices]:
            raise serializers.ValidationError(
                f"Invalid size choice. Must be one of: {[choice[0] for choice in MarketplaceProduct.SizeChoices.choices]}"
            )
        return value

    def validate_color(self, value):
        """
        Validate color choice if provided
        """
        if value and value not in [choice[0] for choice in MarketplaceProduct.ColorChoices.choices]:
            raise serializers.ValidationError(
                f"Invalid color choice. Must be one of: {[choice[0] for choice in MarketplaceProduct.ColorChoices.choices]}"
            )
        return value

    def validate(self, data):
        """
        Custom validation for marketplace product
        """
        # Auto-inherit size and color from product if not provided
        product = data.get("product")
        if product:
            if not data.get("size") and product.size:
                data["size"] = product.size
            if not data.get("color") and product.color:
                data["color"] = product.color
            if not data.get("additional_information") and product.additional_information:
                data["additional_information"] = product.additional_information

        return super().validate(data)

    # def to_representation(self, instance):
    #     """
    #     Override to conditionally include B2B fields based on user eligibility
    #     """
    #     data = super().to_representation(instance)

    #     # Check if user is eligible for B2B pricing
    #     user = self.context.get("request", {}).user if self.context.get("request") else None
    #     show_b2b_fields = False

    #     # Debug information (remove in production)
    #     debug_info = {
    #         "user_authenticated": False,
    #         "user_has_profile": False,
    #         "user_b2b_verified": False,
    #         "product_enable_b2b": instance.enable_b2b_sales,
    #     }

    #     if user and user.is_authenticated:
    #         debug_info["user_authenticated"] = True
    #         try:
    #             profile = getattr(user, "user_profile", None)
    #             if profile:
    #                 debug_info["user_has_profile"] = True
    #                 b2b_verified = getattr(profile, "b2b_verified", False)
    #                 debug_info["user_b2b_verified"] = b2b_verified

    #                 if b2b_verified and instance.enable_b2b_sales:
    #                     show_b2b_fields = True
    #         except AttributeError:
    #             pass

    #     # Add debug info to response (remove in production)
    #     data["_debug_b2b"] = debug_info
    #     data["_show_b2b_fields"] = show_b2b_fields

    #     # Remove B2B fields if user is not eligible
    #     if not show_b2b_fields:
    #         data.pop("b2b_price", None)
    #         data.pop("b2b_min_quantity", None)
    #         data.pop("b2b_price_tiers", None)

    #     return data


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ["id", "name"]


class CreateMarketplaceProductFromProductSerializer(serializers.Serializer):
    """
    Serializer for creating a MarketplaceProduct from an existing Product.
    Inherits brand information automatically from the source product.
    """

    product_id = serializers.IntegerField()
    listed_price = serializers.FloatField(required=False, help_text="Override the product price if needed")
    discounted_price = serializers.FloatField(required=False, allow_null=True, help_text="Optional discounted price")
    size = serializers.ChoiceField(choices=MarketplaceProduct.SizeChoices.choices, required=False, allow_null=True)
    color = serializers.ChoiceField(choices=MarketplaceProduct.ColorChoices.choices, required=False, allow_null=True)
    additional_information = serializers.CharField(
        required=False, allow_blank=True, help_text="Additional marketplace-specific information"
    )
    min_order = serializers.IntegerField(required=False, allow_null=True, help_text="Minimum order quantity")
    offer_start = serializers.DateTimeField(required=False, allow_null=True)
    offer_end = serializers.DateTimeField(required=False, allow_null=True)
    estimated_delivery_days = serializers.IntegerField(required=False, allow_null=True)
    shipping_cost = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    is_featured = serializers.BooleanField(required=False, default=False)
    is_made_in_nepal = serializers.BooleanField(required=False, default=False)

    # Read-only fields for confirmation
    source_brand_name = serializers.SerializerMethodField(read_only=True)
    source_brand_verified = serializers.SerializerMethodField(read_only=True)

    def get_source_brand_name(self, obj):
        """Get brand name from source product"""
        product_id = obj.get("product_id")
        if product_id:
            try:
                product = Product.objects.get(id=product_id)
                return product.get_brand_name()
            except Product.DoesNotExist:
                pass
        return "Unbranded"

    def get_source_brand_verified(self, obj):
        """Get brand verification status from source product"""
        product_id = obj.get("product_id")
        if product_id:
            try:
                product = Product.objects.get(id=product_id)
                return product.brand.is_verified if product.brand else False
            except Product.DoesNotExist:
                pass
        return False

    def validate_product_id(self, value):
        """
        Validate that the product exists and can be used to create a marketplace product
        """
        try:
            product = Product.objects.get(id=value)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product with this ID does not exist.")

        # Check if marketplace product already exists
        if MarketplaceProduct.objects.filter(product_id=value).exists():
            raise serializers.ValidationError("A marketplace product already exists for this product.")

        # Check if product is active
        if not product.is_active:
            raise serializers.ValidationError("Cannot create marketplace product from inactive product.")

        return value

    def validate(self, data):
        """
        Cross-field validation
        """
        # Validate offer dates
        offer_start = data.get("offer_start")
        offer_end = data.get("offer_end")

        if offer_start and offer_end and offer_start >= offer_end:
            raise serializers.ValidationError("Offer end date must be after offer start date.")

        # Validate pricing
        listed_price = data.get("listed_price")
        discounted_price = data.get("discounted_price")

        if discounted_price and listed_price and discounted_price >= listed_price:
            raise serializers.ValidationError("Discounted price must be less than listed price.")

        return data

    def create(self, validated_data):
        """
        Create MarketplaceProduct from Product data
        """
        product_id = validated_data.pop("product_id")
        product = Product.objects.get(id=product_id)

        # Set default listed_price from product if not provided
        if "listed_price" not in validated_data:
            validated_data["listed_price"] = product.price

        # Inherit size, color, and additional_information from product if not provided
        if "size" not in validated_data and product.size:
            validated_data["size"] = product.size

        if "color" not in validated_data and product.color:
            validated_data["color"] = product.color

        if "additional_information" not in validated_data and product.additional_information:
            validated_data["additional_information"] = product.additional_information

        # Set the product reference
        validated_data["product"] = product

        # Create the marketplace product
        marketplace_product = MarketplaceProduct.objects.create(**validated_data)

        return marketplace_product


class LedgerEntrySerializer(serializers.ModelSerializer):
    account_type_display = serializers.CharField(source="get_account_type_display", read_only=True)

    class Meta:
        model = LedgerEntry
        fields = ["id", "account_type", "amount", "debit", "reference_id", "date", "related_entity", "account_type_display"]


class AuditLogSerializer(serializers.ModelSerializer):
    transaction_type = serializers.ChoiceField(choices=AuditLog.TransactionType.choices)

    class Meta:
        model = AuditLog
        fields = ["id", "transaction_type", "reference_id", "date", "entity_id", "amount"]


class ProcurementRequestSerializer(serializers.Serializer):
    producer_id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    unit_cost = serializers.DecimalField(max_digits=10, decimal_places=2)


class ProcurementResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["id", "order_number", "customer", "product", "quantity", "status", "total_price"]


class SalesRequestSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    selling_price = serializers.DecimalField(max_digits=10, decimal_places=2)


class SalesResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sale
        fields = ["id", "order", "quantity", "sale_price", "sale_date", "payment_status"]


class ReconciliationResponseSerializer(serializers.Serializer):
    net_vat = serializers.DecimalField(max_digits=12, decimal_places=2)
    tds_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    profit = serializers.DecimalField(max_digits=12, decimal_places=2)


class DirectSaleSerializer(serializers.ModelSerializer):
    """
    Serializer for DirectSale model.
    Handles creation and updating of direct sales.
    """

    product_details = ProductSerializer(source="product", read_only=True)
    user_username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = DirectSale
        fields = [
            "id",
            "product",
            "quantity",
            "unit_price",
            "total_amount",
            "sale_date",
            "reference",
            "notes",
            "user",
            "product_details",
            "user_username",
        ]
        read_only_fields = ["total_amount", "user"]

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate(self, data):
        """
        Validate that there's enough stock before creating a sale.
        """
        if self.instance is None:
            product = data.get("product")
            quantity = data.get("quantity")

            if product and quantity:
                if product.stock < quantity:
                    raise serializers.ValidationError({"quantity": f"Not enough stock. Only {product.stock} available."})
        return data

    def create(self, validated_data):
        """
        Create a new DirectSale instance.
        Sets the current user as the seller and calculates total amount.
        """
        validated_data["user"] = self.context["request"].user

        if "total_amount" not in validated_data:
            validated_data["total_amount"] = validated_data["quantity"] * validated_data["unit_price"]

        return super().create(validated_data)


class PurchaseOrderSerializer(serializers.ModelSerializer):
    product_details = ProductSerializer(source="product", read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = "__all__"


class ShopQRSerializer(serializers.ModelSerializer):
    qr_image_url = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = ["payment_qr_payload", "qr_image_url"]

    def get_qr_image_url(self, obj):
        req = self.context.get("request")
        if obj.payment_qr_image and req:
            return req.build_absolute_uri(obj.payment_qr_image.url)
        return None


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "order", "amount", "method", "status"]
        read_only_fields = ["id", "status"]


class KhaltiInitSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()


class KhaltiVerifySerializer(serializers.Serializer):
    payment_id = serializers.IntegerField()
    token = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
