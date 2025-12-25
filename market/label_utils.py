import io

import qrcode
from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .models import Delivery, MarketplaceOrder, MarketplaceSale


def generate_shipping_label_for_marketplace_sale(marketplace_sale_id):
    try:
        sale = MarketplaceSale.objects.get(id=marketplace_sale_id)
        delivery = sale.delivery
        if not delivery:
            return None
    except MarketplaceSale.DoesNotExist:
        return None

    # Quarter A4 label (half width x half height of A4)
    buffer = io.BytesIO()
    label_width = int(595 / 2)  # ~297 points
    label_height = int(842 / 2)  # ~421 points
    c = canvas.Canvas(buffer, pagesize=(label_width, label_height))

    margin_left = 12
    y = label_height - 20
    # Header / branding
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin_left, y, "Mulyabazzar")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(margin_left, y, f"Order: {sale.order_number}")
    y -= 11
    c.drawString(margin_left, y, f"Recipient: {delivery.customer_name}")
    y -= 10
    c.drawString(margin_left, y, f"Phone: {delivery.phone_number}")
    y -= 10
    addr = f"{delivery.address}, {delivery.city}, {delivery.state}, {delivery.zip_code}"
    c.drawString(margin_left, y, addr[:80])
    y -= 12
    c.drawString(margin_left, y, f"Tracking: {delivery.tracking_number or 'N/A'}")
    y -= 11
    c.drawString(margin_left, y, f"Amount: {sale.total_amount} {sale.currency}")
    y -= 12
    # QR code (smaller)
    qr_img = qrcode.make(f"{delivery.tracking_number or sale.order_number}")
    if not isinstance(qr_img, Image.Image):
        qr_img = qr_img.get_image()
    c.drawInlineImage(qr_img, label_width - 80, label_height - 110, 64, 64)
    c.save()
    buffer.seek(0)
    return ContentFile(buffer.read(), name=f"label_{sale.order_number}.pdf")


def generate_shipping_label_for_marketplace_order(order_id):
    try:
        order = MarketplaceOrder.objects.get(id=order_id)
        delivery = order.delivery
        if not delivery:
            return None
    except MarketplaceOrder.DoesNotExist:
        return None

    buffer = io.BytesIO()

    # Quarter A4 size (A4 is 595x842 points)
    label_width = int(595 / 2)  # 297.5 points (~105mm)
    label_height = int(842 / 2)  # 421 points (~148.5mm)
    c = canvas.Canvas(buffer, pagesize=(label_width, label_height))

    # Margins
    margin_left = 10
    margin_right = label_width - 10

    # Starting position from top
    y_pos = label_height - 15

    # Header Section - Sales Order/Marketplace
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin_left, y_pos, "Sales Order")
    y_pos -= 15

    # Top Barcode (Order Number as Code128 barcode)
    try:
        from reportlab.graphics.barcode import code128

        barcode_order = code128.Code128(order.order_number, barHeight=25, barWidth=0.8)
        barcode_order.drawOn(c, margin_left, y_pos - 35)
    except:
        # Fallback if barcode generation fails
        c.setFont("Helvetica", 8)
        c.drawString(margin_left, y_pos - 25, f"*{order.order_number}*")

    y_pos -= 45

    # Tracking Number
    c.setFont("Helvetica", 7)
    c.drawString(margin_left, y_pos, "Tracking Number:")
    c.setFont("Helvetica-Bold", 9)
    tracking_num = order.tracking_number or order.order_number
    c.drawString(margin_left + 65, y_pos, tracking_num)
    y_pos -= 18

    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_left, y_pos, "Mulyabazzar")
    y_pos -= 12

    # Separator line
    c.line(margin_left, y_pos, margin_right, y_pos)
    y_pos -= 12

    # Product/Order Code
    c.setFont("Helvetica-Bold", 8)
    c.drawString(margin_left, y_pos, order.order_number)
    y_pos -= 13

    # Price
    c.setFont("Helvetica", 8)
    c.drawString(margin_left, y_pos, f"Rs.{order.total_amount} {order.currency}")
    y_pos -= 18

    # QR Code Section (left side) + Recipient Info (right side)
    qr_data = f"Order: {order.order_number}\nTracking: {tracking_num}\nAmount: Rs.{order.total_amount} {order.currency}"
    qr_img = qrcode.make(qr_data)
    if not isinstance(qr_img, Image.Image):
        qr_img = qr_img.get_image()

    # Draw QR code on left side (smaller for quarter A4)
    qr_size = 45
    c.drawInlineImage(qr_img, margin_left, y_pos - qr_size, qr_size, qr_size)

    # Recipient Information (right side of QR)
    info_x = margin_left + qr_size + 8
    info_y = y_pos - 5

    c.setFont("Helvetica", 6)
    c.drawString(info_x, info_y, "Recipient")
    info_y -= 11

    c.setFont("Helvetica-Bold", 8)
    # Truncate long names to fit
    customer_name = delivery.customer_name[:25]
    c.drawString(info_x, info_y, customer_name)
    info_y -= 10

    c.setFont("Helvetica", 7)
    # Address formatting - adjust character limits for quarter A4
    max_chars_per_line = 30
    address_line1 = delivery.address[:max_chars_per_line]
    c.drawString(info_x, info_y, address_line1)
    info_y -= 9

    if len(delivery.address) > max_chars_per_line:
        address_line2 = delivery.address[max_chars_per_line : max_chars_per_line * 2]
        c.drawString(info_x, info_y, address_line2)
        info_y -= 9

    # City, State
    location = f"{delivery.city}, {delivery.state}"
    c.drawString(info_x, info_y, location[:30])
    info_y -= 9

    # Phone
    c.drawString(info_x, info_y, f"Ph: {delivery.phone_number}")

    y_pos -= qr_size + 15

    # Footer - Dates
    c.setFont("Helvetica", 6)
    from datetime import datetime

    print_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.drawString(margin_left, y_pos, f"Print: {print_date}")
    y_pos -= 8

    if hasattr(order, "created_at"):
        order_date = order.created_at.strftime("%Y-%m-%d")
        c.drawString(margin_left, y_pos, f"Order: {order_date}")

    # Payment method indicator (COD badge)
    y_pos -= 3
    payment_badge_x = margin_right - 30
    if order.payment_method or "COD" in order.payment_method.upper():
        c.setFillColorRGB(0, 0, 0)
        c.rect(payment_badge_x, y_pos, 25, 9, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 6)
        c.drawString(payment_badge_x + 3, y_pos + 2, "COD")
        c.setFillColorRGB(0, 0, 0)

    c.save()
    buffer.seek(0)
    return ContentFile(buffer.read(), name=f"label_{order.order_number}.pdf")
