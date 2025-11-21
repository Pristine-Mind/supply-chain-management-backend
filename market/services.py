import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db import transaction
from django.template.loader import get_template, render_to_string
from django.utils import timezone

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

logger = logging.getLogger(__name__)


class SparrowSMS:
    def __init__(self):
        # Load from your Django settings
        self.api_url = settings.SPARROWSMS_ENDPOINT
        self.sender = settings.SPARROWSMS_SENDER_ID
        self.api_key = settings.SPARROWSMS_API_KEY
        self.message = None
        self.recipient = None

    def set_message(self, message: str):
        self.message = message

    def set_recipient(self, phone: str):
        self.recipient = phone

    def send_message(self) -> dict:
        """
        Send the SMS via SparrowSMS REST API.
        Returns a dict with keys: code, status, message, sms_code
        """
        if not all([self.api_url, self.sender, self.api_key, self.recipient, self.message]):
            raise ValueError("API credentials, recipient, and message must all be set.")

        payload = {
            "token": self.api_key,
            "to": self.recipient,
            "text": self.message,
            "from": self.sender,
        }

        headers = {
            "Authorization": self.api_key,
            "Idempotency-Key": str(uuid.uuid4()),
            "Accept": "application/json",
            "Accept-Language": "en-us",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(self.api_url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            # Attempt to parse Sparrow’s error response
            try:
                data = e.response.json()
            except Exception:
                return {"code": 500, "status": "error", "message": f"Network or parsing error: {e}", "sms_code": None}

        code = str(data.get("response_code", ""))
        mapping = {
            "200": {"code": 200, "status": "success", "message": "Message sent successfully", "sms_code": "200"},
            "1007": {"code": 401, "status": "error", "message": "Invalid Receiver", "sms_code": "1007"},
            "1607": {"code": 401, "status": "error", "message": "Authentication Failure", "sms_code": "1607"},
            "1002": {"code": 401, "status": "error", "message": "Invalid Token", "sms_code": "1002"},
            "1011": {"code": 401, "status": "error", "message": "Unknown Receiver", "sms_code": "1011"},
        }

        return mapping.get(
            code,
            {"code": 400, "status": "error", "message": data.get("message", "Unknown error"), "sms_code": code or "0000"},
        )


class InvoiceGenerationService:
    """
    Service for generating invoices from sales and payments.
    Designed to work from Django admin panel and automatic triggers.
    """

    @staticmethod
    def create_invoice_from_payment_transaction(payment_transaction):
        """
        Create invoice from completed payment transaction (new system)
        Enhanced to fetch comprehensive data from Cart and CartItem
        """
        from .models import Invoice, InvoiceLineItem

        if payment_transaction.status != "completed":
            raise ValueError("Can only create invoices for completed payments")

        # Check if invoice already exists
        existing_invoice = Invoice.objects.filter(payment_transaction=payment_transaction).first()
        if existing_invoice:
            logger.info(f"Invoice already exists for payment {payment_transaction.order_number}")
            return existing_invoice

        with transaction.atomic():
            # Get comprehensive customer and delivery information
            customer_info = InvoiceGenerationService._extract_customer_info_from_payment(payment_transaction)
            billing_address = InvoiceGenerationService._get_billing_address_from_payment(payment_transaction)

            # Create invoice with comprehensive data
            invoice = Invoice.objects.create(
                payment_transaction=payment_transaction,
                customer=payment_transaction.user,
                customer_name=customer_info["name"],
                customer_email=customer_info["email"],
                customer_phone=customer_info["phone"],
                billing_address=billing_address,
                due_date=timezone.now() + timedelta(days=30),  # Set due date to 30 days from now
                subtotal=payment_transaction.subtotal,
                tax_amount=payment_transaction.tax_amount,
                shipping_cost=payment_transaction.shipping_cost,
                total_amount=payment_transaction.total_amount,
                currency="NPR",
                status="paid",  # Since payment is completed
            )

            # Create line items from cart items with detailed product information
            if payment_transaction.cart:
                cart_items = payment_transaction.cart.items.select_related(
                    "product__product", "product__product__user"
                ).all()

                for cart_item in cart_items:
                    # Get current product price or marketplace product price
                    unit_price = cart_item.product.product.price

                    # Create line item with comprehensive product data
                    InvoiceLineItem.objects.create(
                        invoice=invoice,
                        product_name=cart_item.product.product.name,
                        product_sku=getattr(cart_item.product.product, "sku", f"MP-{cart_item.product.id}"),
                        description=InvoiceGenerationService._format_product_description(cart_item.product),
                        quantity=cart_item.quantity,
                        unit_price=unit_price,
                        marketplace_product=cart_item.product,
                    )

            # Generate PDF
            if PDF_AVAILABLE:
                InvoiceGenerationService.generate_invoice_pdf(invoice)
            else:
                logger.warning("PDF generation unavailable - ReportLab not installed")

            logger.info(f"Invoice {invoice.invoice_number} created for payment {payment_transaction.order_number}")
            return invoice

    @staticmethod
    def create_invoice_from_marketplace_sale(marketplace_sale):
        """
        Create invoice from marketplace sale (legacy system)
        Enhanced to fetch related data and delivery information
        """
        from .models import Invoice, InvoiceLineItem

        # Accept both "completed" and "paid" status for invoice generation
        if marketplace_sale.payment_status not in ["completed", "paid"]:
            raise ValueError(
                f"Can only create invoices for completed/paid sales. Current status: {marketplace_sale.payment_status}"
            )

        # Check if invoice already exists
        existing_invoice = getattr(marketplace_sale, "invoice", None)
        if existing_invoice:
            logger.info(f"Invoice already exists for sale {marketplace_sale.order_number}")
            return existing_invoice

        with transaction.atomic():
            # Get comprehensive customer information
            customer_info = InvoiceGenerationService._extract_customer_info_from_sale(marketplace_sale)
            billing_address = InvoiceGenerationService._get_billing_address_from_sale(marketplace_sale)

            # Create invoice with comprehensive data
            invoice = Invoice.objects.create(
                marketplace_sale=marketplace_sale,
                customer=marketplace_sale.buyer,
                customer_name=customer_info["name"],
                customer_email=customer_info["email"],
                customer_phone=customer_info["phone"],
                billing_address=billing_address,
                due_date=timezone.now() + timedelta(days=30),  # Set due date to 30 days from now
                subtotal=marketplace_sale.subtotal,
                tax_amount=marketplace_sale.tax_amount,
                shipping_cost=marketplace_sale.shipping_cost,
                total_amount=marketplace_sale.total_amount,
                currency=marketplace_sale.currency,
                status="paid",
            )

            # Create line item with comprehensive product data
            InvoiceLineItem.objects.create(
                invoice=invoice,
                product_name=marketplace_sale.product.product.name,
                product_sku=getattr(marketplace_sale.product.product, "sku", f"MP-{marketplace_sale.product.id}"),
                description=InvoiceGenerationService._format_product_description(marketplace_sale.product),
                quantity=marketplace_sale.quantity,
                unit_price=marketplace_sale.unit_price,
                marketplace_product=marketplace_sale.product,
            )

            # Generate PDF
            if PDF_AVAILABLE:
                InvoiceGenerationService.generate_invoice_pdf(invoice)
            else:
                logger.warning("PDF generation unavailable - ReportLab not installed")

            logger.info(f"Invoice {invoice.invoice_number} created for sale {marketplace_sale.order_number}")
            return invoice

    @staticmethod
    def generate_invoice_pdf(invoice):
        if not PDF_AVAILABLE:
            logger.error("Cannot generate PDF - ReportLab not installed")
            return False

        try:
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
            styles = getSampleStyleSheet()
            story = []

            # Define colors - Orange theme
            primary_color = colors.HexColor("#ff8c00")  # Dark orange
            light_orange = colors.HexColor("#ffa500")  # Orange
            text_dark = colors.HexColor("#1a202c")
            text_gray = colors.HexColor("#718096")
            bg_light = colors.HexColor("#f7fafc")
            bg_gray = colors.HexColor("#edf2f7")

            # Header section - Orange background with INVOICE and MulyaBazzar
            header_content = [
                [
                    Paragraph(
                        "<b>INVOICE</b><br/><font size='8'>MulyaBazzar</font>",
                        ParagraphStyle(
                            "HeaderTitle",
                            parent=styles["Normal"],
                            fontSize=28,
                            textColor=colors.white,
                            fontName="Helvetica-Bold",
                            leading=32,
                        ),
                    ),
                    Paragraph(
                        "✓ PAID",
                        ParagraphStyle(
                            "StatusBadge",
                            parent=styles["Normal"],
                            fontSize=11,
                            textColor=colors.white,
                            fontName="Helvetica-Bold",
                            alignment=2,
                        ),
                    ),
                ]
            ]

            header_table = Table(header_content, colWidths=[4.5 * inch, 1.5 * inch])
            header_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), primary_color),
                        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                        ("ALIGN", (0, 0), (0, -1), "LEFT"),
                        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 20),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
                        ("TOPPADDING", (0, 0), (-1, -1), 25),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 25),
                    ]
                )
            )

            story.append(header_table)
            story.append(Spacer(1, 30))

            # Invoice details in 2x2 grid below header
            detail_data = [
                ["Invoice Number:", invoice.invoice_number, "Invoice Date:", invoice.invoice_date.strftime("%Y-%m-%d")],
                ["Order Number:", invoice.source_order_number or "N/A", "Status:", invoice.get_status_display()],
            ]

            detail_table = Table(detail_data, colWidths=[1.2 * inch, 1.6 * inch, 1.2 * inch, 1.6 * inch])
            detail_table.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                        ("FONTNAME", (3, 0), (3, -1), "Helvetica"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("TEXTCOLOR", (0, 0), (-1, -1), text_dark),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ]
                )
            )

            story.append(detail_table)
            story.append(Spacer(1, 25))

            # Billing section
            billing_header_style = ParagraphStyle(
                "BillingHeader",
                parent=styles["Normal"],
                fontSize=9,
                textColor=text_gray,
                fontName="Helvetica-Bold",
                spaceAfter=10,
                letterSpacing=1,
            )

            customer_name_style = ParagraphStyle(
                "CustomerName",
                parent=styles["Normal"],
                fontSize=13,
                textColor=text_dark,
                fontName="Helvetica-Bold",
                spaceAfter=8,
            )

            customer_info_style = ParagraphStyle(
                "CustomerInfo", parent=styles["Normal"], fontSize=10, textColor=text_dark, spaceAfter=4
            )

            billing_content = [
                [Paragraph("BILL TO", billing_header_style)],
                [Spacer(1, 8)],
                [Paragraph(invoice.customer_name, customer_name_style)],
                [Spacer(1, 4)],
                [Paragraph(invoice.customer_email, customer_info_style)],
                [Spacer(1, 2)],
            ]

            if invoice.customer_phone:
                billing_content.append([Paragraph(invoice.customer_phone, customer_info_style)])

            billing_table = Table(billing_content, colWidths=[5.5 * inch])
            billing_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), bg_light),
                        ("LEFTPADDING", (0, 0), (-1, -1), 20),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
                        ("TOPPADDING", (0, 0), (0, 0), 20),
                        ("TOPPADDING", (0, 1), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -2), 0),
                        ("BOTTOMPADDING", (0, -1), (-1, -1), 20),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )

            story.append(billing_table)
            story.append(Spacer(1, 25))

            # Items table
            items_data = [["ITEM", "SKU", "QTY", "UNIT PRICE", "TOTAL"]]

            for item in invoice.line_items.all():
                items_data.append(
                    [
                        item.product_name,
                        item.product_sku or "-",
                        str(item.quantity),
                        f"NPR\n{item.unit_price:,.2f}",
                        f"NPR\n{item.total_price:,.2f}",
                    ]
                )

            items_table = Table(items_data, colWidths=[2 * inch, 1 * inch, 0.7 * inch, 1 * inch, 1 * inch])
            items_table.setStyle(
                TableStyle(
                    [
                        # Header row
                        ("BACKGROUND", (0, 0), (-1, 0), bg_gray),
                        ("TEXTCOLOR", (0, 0), (-1, 0), text_gray),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 9),
                        ("ALIGN", (0, 0), (0, 0), "LEFT"),
                        ("ALIGN", (1, 0), (2, 0), "CENTER"),
                        ("ALIGN", (3, 0), (-1, 0), "RIGHT"),
                        ("TOPPADDING", (0, 0), (-1, 0), 12),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                        # Data rows
                        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 1), (-1, -1), 9),
                        ("TEXTCOLOR", (0, 1), (-1, -1), text_dark),
                        ("ALIGN", (0, 1), (0, -1), "LEFT"),
                        ("ALIGN", (1, 1), (2, -1), "CENTER"),
                        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                        ("TOPPADDING", (0, 1), (-1, -1), 15),
                        ("BOTTOMPADDING", (0, 1), (-1, -1), 15),
                        ("LEFTPADDING", (0, 0), (-1, -1), 15),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 15),
                        # Borders
                        ("LINEBELOW", (0, 1), (-1, -2), 0.5, colors.HexColor("#e2e8f0")),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ]
                )
            )

            story.append(items_table)
            story.append(Spacer(1, 25))

            # Summary section
            summary_data = []

            if invoice.subtotal != invoice.total_amount:
                summary_data.append(["Subtotal", f"NPR {invoice.subtotal:,.2f}"])

            if invoice.shipping_cost > 0:
                summary_data.append(["Shipping", f"NPR {invoice.shipping_cost:,.2f}"])

            summary_data.append(["", ""])  # Spacer row
            summary_data.append(["Total Amount", f"NPR {invoice.total_amount:,.2f}"])

            summary_table = Table(summary_data, colWidths=[4.2 * inch, 1.3 * inch])
            summary_table.setStyle(
                TableStyle(
                    [
                        # Regular rows
                        ("ALIGN", (0, 0), (0, -2), "RIGHT"),
                        ("ALIGN", (1, 0), (1, -2), "RIGHT"),
                        ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
                        ("FONTSIZE", (0, 0), (-1, -2), 10),
                        ("TEXTCOLOR", (0, 0), (-1, -2), text_gray),
                        ("TOPPADDING", (0, 0), (-1, -2), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -2), 8),
                        # Total row
                        ("ALIGN", (0, -1), (-1, -1), "RIGHT"),
                        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                        ("FONTSIZE", (0, -1), (-1, -1), 14),
                        ("TEXTCOLOR", (0, -1), (-1, -1), text_dark),
                        ("TOPPADDING", (0, -1), (-1, -1), 15),
                        ("BOTTOMPADDING", (0, -1), (-1, -1), 15),
                        ("LINEABOVE", (0, -1), (-1, -1), 2, colors.HexColor("#cbd5e0")),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 15),
                        ("LEFTPADDING", (0, 0), (-1, -1), 15),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ]
                )
            )

            story.append(summary_table)
            story.append(Spacer(1, 40))

            # Footer
            footer_title_style = ParagraphStyle(
                "FooterTitle",
                parent=styles["Normal"],
                fontSize=13,
                textColor=text_dark,
                fontName="Helvetica-Bold",
                alignment=1,
                spaceAfter=6,
            )

            footer_text_style = ParagraphStyle(
                "FooterText",
                parent=styles["Normal"],
                fontSize=9,
                textColor=text_gray,
                fontName="Helvetica",
                alignment=1,
                spaceAfter=2,
            )

            footer_data = [
                [Paragraph("Thank you for your business!", footer_title_style)],
                [Spacer(1, 4)],
                [Paragraph("MulyaBazzar Team", footer_text_style)],
                [Paragraph("For inquiries, please contact our support team", footer_text_style)],
            ]

            footer_table = Table(footer_data, colWidths=[5.5 * inch])
            footer_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), bg_light),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 20),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
                        ("TOPPADDING", (0, 0), (0, 0), 20),
                        ("TOPPADDING", (0, 1), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -2), 0),
                        ("BOTTOMPADDING", (0, -1), (-1, -1), 20),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ]
                )
            )

            story.append(footer_table)

            # Build PDF
            doc.build(story)

            # Save PDF to model
            buffer.seek(0)
            filename = f"invoice_{invoice.invoice_number}.pdf"
            invoice.pdf_file.save(filename, ContentFile(buffer.getvalue()), save=True)
            buffer.close()

            logger.info(f"PDF generated for invoice {invoice.invoice_number}")
            return True

        except Exception as e:
            logger.error(f"Error generating PDF for invoice {invoice.invoice_number}: {str(e)}")
            return False

    @staticmethod
    def send_invoice_email(invoice, resend=False):
        """
        Send invoice via email
        """
        try:
            subject = f"Invoice {invoice.invoice_number} - Supply Chain Management"

            # Create email content
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@supplychain.com")
            to_email = invoice.customer_email

            # Simple email content
            message = f"""Dear {invoice.customer_name},

            {'Thank you for your purchase! ' if not resend else 'As requested, '}Please find your invoice attached.

            Invoice Details:
            - Invoice Number: {invoice.invoice_number}
            - Total Amount: {invoice.currency} {invoice.total_amount:,.2f}
            - Date: {invoice.invoice_date.strftime('%Y-%m-%d')}

            If you have any questions, please contact our support team.

            Best regards,
            Supply Chain Management Team
            """

            email = EmailMessage(
                subject=subject,
                body=message,
                from_email=from_email,
                to=[to_email],
            )

            # Attach PDF if available
            if invoice.pdf_file:
                try:
                    email.attach_file(invoice.pdf_file.path)
                except Exception as e:
                    logger.warning(f"Could not attach PDF file: {str(e)}")

            # Send email
            email.send()

            # Update invoice status
            if not resend:
                invoice.sent_at = timezone.now()
                if invoice.status == "draft":
                    invoice.status = "sent"
                invoice.save(update_fields=["sent_at", "status"])

            logger.info(f"Invoice {invoice.invoice_number} {'resent' if resend else 'sent'} to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Error sending invoice email: {str(e)}")
            return False

    @staticmethod
    def bulk_generate_invoices(queryset):
        """
        Bulk generate invoices for admin actions
        """
        results = {"success": 0, "errors": 0, "messages": []}

        for obj in queryset:
            try:
                # Determine object type and generate invoice accordingly
                if hasattr(obj, "payment_status"):  # MarketplaceSale
                    if obj.payment_status == "completed":
                        invoice = InvoiceGenerationService.create_invoice_from_marketplace_sale(obj)
                        results["success"] += 1
                        results["messages"].append(f"Invoice {invoice.invoice_number} created for sale {obj.order_number}")
                    else:
                        results["errors"] += 1
                        results["messages"].append(f"Sale {obj.order_number} is not completed")

                elif hasattr(obj, "status") and hasattr(obj, "order_number"):  # PaymentTransaction
                    if obj.status == "completed":
                        invoice = InvoiceGenerationService.create_invoice_from_payment_transaction(obj)
                        results["success"] += 1
                        results["messages"].append(
                            f"Invoice {invoice.invoice_number} created for payment {obj.order_number}"
                        )
                    else:
                        results["errors"] += 1
                        results["messages"].append(f"Payment {obj.order_number} is not completed")

                else:
                    results["errors"] += 1
                    results["messages"].append(f"Unsupported object type: {type(obj)}")

            except Exception as e:
                results["errors"] += 1
                results["messages"].append(f"Error processing {obj}: {str(e)}")

        return results

    @staticmethod
    def _get_billing_address(payment_transaction):
        """Extract billing address from payment transaction"""
        try:
            if hasattr(payment_transaction, "cart") and payment_transaction.cart:
                return "Address will be updated based on delivery information"
            return "No address provided"
        except:
            return "Address unavailable"

    @staticmethod
    def _get_billing_address_from_payment(payment_transaction):
        """Extract comprehensive billing address from payment transaction and related cart/delivery data"""
        try:
            # Try to get delivery information from cart
            if payment_transaction.cart:
                # Check if there's delivery information linked to the cart
                delivery = getattr(payment_transaction.cart, "delivery", None)
                if delivery and hasattr(delivery, "first"):
                    delivery = delivery.first()

                if delivery:
                    return f"{delivery.address}, {delivery.city}, {delivery.state} {delivery.zip_code}"

            # Fallback to payment transaction customer info if available
            if payment_transaction.customer_name:
                return f"Customer: {payment_transaction.customer_name}"

            return "Address will be updated based on delivery information"
        except Exception as e:
            logger.warning(f"Error extracting billing address: {str(e)}")
            return "Address unavailable"

    @staticmethod
    def _get_billing_address_from_sale(marketplace_sale):
        """Extract billing address from marketplace sale and related data"""
        try:
            # Try to find any delivery/shipping information related to this sale
            # This could be enhanced based on your specific delivery model relationships

            # Check if buyer has profile with address information
            if marketplace_sale.buyer:
                try:
                    # If user has profile with address information
                    if hasattr(marketplace_sale.buyer, "profile"):
                        profile = marketplace_sale.buyer.profile
                        if hasattr(profile, "address"):
                            return profile.address
                except:
                    pass

            # Use buyer information from the sale
            address_parts = []
            if marketplace_sale.buyer_name:
                address_parts.append(f"Customer: {marketplace_sale.buyer_name}")
            if marketplace_sale.buyer_email:
                address_parts.append(f"Email: {marketplace_sale.buyer_email}")
            if marketplace_sale.buyer_phone:
                address_parts.append(f"Phone: {marketplace_sale.buyer_phone}")

            return ", ".join(address_parts) if address_parts else "Address to be provided"

        except Exception as e:
            logger.warning(f"Error extracting billing address from sale: {str(e)}")
            return "Address unavailable"

    @staticmethod
    def _get_billing_address_from_order(marketplace_order):
        """Extract billing address from marketplace order"""
        try:
            if hasattr(marketplace_order, "delivery") and marketplace_order.delivery:
                delivery = marketplace_order.delivery
                return f"{delivery.address}, {delivery.city}, {delivery.state} {delivery.zip_code}"
            return "Address will be updated based on delivery information"
        except Exception as e:
            logger.warning(f"Error extracting billing address from order: {str(e)}")
            return "Address unavailable"

    @staticmethod
    def _extract_customer_info_from_payment(payment_transaction):
        """Extract comprehensive customer information from payment transaction"""
        try:
            # Get customer name - priority: payment transaction > user profile > username
            name = (
                payment_transaction.customer_name
                or payment_transaction.user.get_full_name()
                or payment_transaction.user.username
            )

            # Get customer email - priority: payment transaction > user email
            email = payment_transaction.customer_email or payment_transaction.user.email

            # Get customer phone - priority: payment transaction > user profile
            phone = payment_transaction.customer_phone or ""
            if not phone and hasattr(payment_transaction.user, "profile"):
                try:
                    phone = str(getattr(payment_transaction.user.profile, "phone", ""))
                except:
                    pass

            # Try to get additional info from cart delivery data
            if payment_transaction.cart:
                delivery = getattr(payment_transaction.cart, "delivery", None)
                if delivery and hasattr(delivery, "first"):
                    delivery = delivery.first()

                if delivery:
                    # Use delivery info if payment info is missing
                    if not name and delivery.customer_name:
                        name = delivery.customer_name
                    if not email and delivery.email:
                        email = delivery.email
                    if not phone and delivery.phone_number:
                        phone = delivery.phone_number

            return {"name": name or "Customer", "email": email or "", "phone": phone or ""}

        except Exception as e:
            logger.warning(f"Error extracting customer info from payment: {str(e)}")
            return {
                "name": payment_transaction.user.username if payment_transaction.user else "Customer",
                "email": payment_transaction.user.email if payment_transaction.user else "",
                "phone": "",
            }

    @staticmethod
    def _extract_customer_info_from_sale(marketplace_sale):
        """Extract comprehensive customer information from marketplace sale"""
        try:
            # Get customer name - priority: sale data > user profile > username
            name = marketplace_sale.buyer_name or marketplace_sale.buyer.get_full_name() or marketplace_sale.buyer.username

            # Get customer email - priority: sale data > user email
            email = marketplace_sale.buyer_email or marketplace_sale.buyer.email

            # Get customer phone from sale or user profile
            phone = str(marketplace_sale.buyer_phone) if marketplace_sale.buyer_phone else ""
            if not phone and hasattr(marketplace_sale.buyer, "profile"):
                try:
                    phone = str(getattr(marketplace_sale.buyer.profile, "phone", ""))
                except:
                    pass

            return {"name": name or "Customer", "email": email or "", "phone": phone or ""}

        except Exception as e:
            logger.warning(f"Error extracting customer info from sale: {str(e)}")
            return {
                "name": marketplace_sale.buyer.username if marketplace_sale.buyer else "Customer",
                "email": marketplace_sale.buyer.email if marketplace_sale.buyer else "",
                "phone": "",
            }

    @staticmethod
    def _format_product_description(marketplace_product):
        """Format comprehensive product description for invoice"""
        try:
            description_parts = []

            # Add basic product description
            if marketplace_product.product.description:
                description_parts.append(marketplace_product.product.description[:200])

            # Add category if available
            if hasattr(marketplace_product.product, "category"):
                category_display = getattr(
                    marketplace_product.product, "get_category_display", lambda: marketplace_product.product.category
                )()
                description_parts.append(f"Category: {category_display}")

            # Add seller information
            if marketplace_product.product.user:
                seller_name = marketplace_product.product.user.get_full_name() or marketplace_product.product.user.username
                description_parts.append(f"Seller: {seller_name}")

            # Add location if available
            if hasattr(marketplace_product.product, "location") and marketplace_product.product.location:
                description_parts.append(f"Location: {marketplace_product.product.location}")

            # Add stock information if available
            if hasattr(marketplace_product.product, "stock"):
                description_parts.append(f"Stock: {marketplace_product.product.stock}")

            return " | ".join(description_parts) or marketplace_product.product.name

        except Exception as e:
            logger.warning(f"Error formatting product description: {str(e)}")
            return marketplace_product.product.name if marketplace_product.product else "Product"
