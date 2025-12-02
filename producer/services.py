"""
Business logic services for producer app, including B2B pricing calculations.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from .models import B2BPriceTier, MarketplaceProduct


class B2BPricingService:
    """Service for handling B2B pricing calculations and business logic."""

    @staticmethod
    def calculate_order_pricing(user: User, items: List[Dict[str, Union[MarketplaceProduct, int]]]) -> Dict[str, Any]:
        """
        Calculate pricing for B2B orders with all applicable discounts.

        Args:
            user: The user placing the order
            items: List of dicts with 'product' (MarketplaceProduct) and 'quantity' (int)

        Returns:
            Dict containing line items, totals, and B2B information
        """
        total = Decimal("0")
        line_items = []
        is_b2b_order = False

        # Check if user is B2B eligible
        try:
            profile = getattr(user, "user_profile", None)
            is_b2b_eligible = profile and getattr(profile, "is_b2b_eligible", False) and profile.business_type
        except AttributeError:
            is_b2b_eligible = False

        for item in items:
            product = item["product"]
            quantity = item["quantity"]

            # Calculate unit price using the product's pricing logic
            unit_price = product.get_effective_price_for_user(user, quantity)
            line_total = unit_price * quantity

            # Check if this item uses B2B pricing
            regular_price = product.price
            is_b2b_price = unit_price != regular_price

            if is_b2b_price:
                is_b2b_order = True

            # Apply additional business-specific discounts
            additional_discount = Decimal("0")
            if is_b2b_eligible and profile.business_type == "distributor":
                # Example: 2% additional discount for distributors on orders over $1000
                if line_total > Decimal("1000"):
                    additional_discount = line_total * Decimal("0.02")
                    line_total -= additional_discount

            line_items.append(
                {
                    "product": product,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "regular_price": regular_price,
                    "line_total": line_total,
                    "additional_discount": additional_discount,
                    "is_b2b_price": is_b2b_price,
                    "savings": (regular_price - unit_price) * quantity if is_b2b_price else Decimal("0"),
                }
            )

            total += line_total

        # Calculate order-level information
        order_info = {
            "line_items": line_items,
            "subtotal": total,
            "is_b2b_order": is_b2b_order,
            "is_b2b_eligible": is_b2b_eligible,
            "total_savings": sum(item["savings"] for item in line_items),
            "customer_type": profile.business_type if is_b2b_eligible else None,
        }

        # Add payment terms if applicable
        if is_b2b_order and is_b2b_eligible:
            order_info.update(
                {
                    "payment_terms_days": profile.payment_terms_days,
                    "credit_limit": profile.credit_limit,
                    "available_credit": profile.get_available_credit(),
                    "can_use_credit": profile.can_use_credit(total),
                }
            )

        return order_info

    @staticmethod
    def get_b2b_pricing_for_product(product: MarketplaceProduct, user: User, quantity: int = 1) -> Dict[str, Any]:
        """
        Get detailed B2B pricing information for a specific product.

        Args:
            product: The marketplace product
            user: The user requesting pricing
            quantity: Quantity for pricing calculation

        Returns:
            Dict containing pricing breakdown and B2B information
        """
        try:
            profile = getattr(user, "user_profile", None)
            is_b2b_eligible = profile and getattr(profile, "is_b2b_eligible", False) and profile.business_type
        except AttributeError:
            is_b2b_eligible = False
            profile = None

        regular_price = product.price
        effective_price = product.get_effective_price_for_user(user, quantity)

        pricing_info = {
            "regular_price": regular_price,
            "effective_price": effective_price,
            "quantity": quantity,
            "line_total": effective_price * quantity,
            "is_b2b_eligible": is_b2b_eligible,
            "is_b2b_pricing": effective_price != regular_price,
            "savings_per_unit": regular_price - effective_price if effective_price != regular_price else Decimal("0"),
            "total_savings": (
                (regular_price - effective_price) * quantity if effective_price != regular_price else Decimal("0")
            ),
        }

        # Add B2B specific information
        if is_b2b_eligible and product.enable_b2b_sales:
            # Get applicable B2B tiers
            b2b_tiers = product.b2b_price_tiers.filter(customer_type=profile.business_type, is_active=True).order_by(
                "min_quantity"
            )

            tier_breakdown = []
            for tier in b2b_tiers:
                tier_info = {
                    "min_quantity": tier.min_quantity,
                    "price_per_unit": tier.price_per_unit,
                    "discount_percentage": tier.discount_percentage,
                    "is_applicable": quantity >= tier.min_quantity,
                    "potential_savings": (
                        (regular_price - tier.price_per_unit) * quantity if quantity >= tier.min_quantity else Decimal("0")
                    ),
                }
                tier_breakdown.append(tier_info)

            pricing_info.update(
                {
                    "customer_type": profile.business_type,
                    "b2b_tiers": tier_breakdown,
                    "payment_terms_days": profile.payment_terms_days,
                    "can_use_credit": profile.can_use_credit(pricing_info["line_total"]),
                }
            )

        return pricing_info

    @staticmethod
    @transaction.atomic
    def apply_credit_to_order(order, credit_amount: Decimal) -> bool:
        """
        Apply business credit to an order.

        Args:
            order: MarketplaceOrder instance
            credit_amount: Amount of credit to apply

        Returns:
            bool: True if credit was successfully applied
        """
        try:
            profile = order.customer.user_profile

            # Validate credit application
            if not profile.is_b2b_eligible():
                return False

            if not profile.has_sufficient_credit(credit_amount):
                return False

            if credit_amount > order.total_amount:
                credit_amount = order.total_amount

            # Apply credit
            profile.credit_used += credit_amount
            profile.save(update_fields=["credit_used"])

            # Update order
            order.credit_applied = credit_amount
            order.is_b2b_order = True
            order.payment_terms_days = profile.payment_terms_days
            order.save(update_fields=["credit_applied", "is_b2b_order", "payment_terms_days"])

            return True

        except Exception:
            return False

    @staticmethod
    def get_credit_terms_summary(user: User) -> Dict[str, Any]:
        """
        Get credit and payment terms summary for a B2B user.

        Args:
            user: The user to get credit info for

        Returns:
            Dict containing credit and terms information
        """
        try:
            profile = getattr(user, "user_profile", None)
            if not profile or not getattr(profile, "is_b2b_eligible", False):
                return {"is_b2b_eligible": False}

            return {
                "is_b2b_eligible": True,
                "business_type": profile.business_type,
                "credit_limit": profile.credit_limit,
                "credit_used": profile.credit_used,
                "available_credit": profile.get_available_credit(),
                "payment_terms_days": profile.payment_terms_days,
                "tax_id": profile.tax_id,
                "is_verified": profile.b2b_verified,
            }

        except AttributeError:
            return {"is_b2b_eligible": False}

    @staticmethod
    def calculate_bulk_discount_breakdown(
        product: MarketplaceProduct, user: User, max_quantity: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Calculate pricing breakdown for different quantities to show bulk discounts.

        Args:
            product: The marketplace product
            user: The user requesting pricing
            max_quantity: Maximum quantity to calculate for

        Returns:
            List of pricing breakdowns for different quantities
        """
        quantity_tiers = [1, 5, 10, 25, 50, 100]
        if max_quantity not in quantity_tiers:
            quantity_tiers.append(max_quantity)
        quantity_tiers = sorted([q for q in quantity_tiers if q <= max_quantity])

        breakdown = []
        for qty in quantity_tiers:
            pricing = B2BPricingService.get_b2b_pricing_for_product(product, user, qty)
            breakdown.append(
                {
                    "quantity": qty,
                    "unit_price": pricing["effective_price"],
                    "total_price": pricing["line_total"],
                    "savings_per_unit": pricing["savings_per_unit"],
                    "total_savings": pricing["total_savings"],
                    "is_b2b_pricing": pricing["is_b2b_pricing"],
                }
            )

        return breakdown
