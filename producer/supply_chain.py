from django.db import transaction, models
from decimal import Decimal
from .models import Producer, Customer, Product, Order, Sale, LedgerEntry, AuditLog

VAT_RATE = Decimal("0.13")
TDS_THRESHOLD = 50000


class SupplyChainService:
    def __init__(self, user):
        self.user = user

    @transaction.atomic
    def procurement_process(self, producer_id, product_id, quantity, unit_cost):
        producer = Producer.objects.get(id=producer_id)
        product = Product.objects.get(id=product_id)
        po_value = Decimal(quantity) * Decimal(unit_cost)

        order = Order.objects.create(
            customer=Customer.objects.filter(user=self.user).first(),
            product=product,
            quantity=quantity,
            status=Order.Status.APPROVED,
            total_price=po_value,
            user=self.user,
        )

        product.stock = models.F("stock") + quantity
        product.cost_price = unit_cost
        product.save()

        LedgerEntry.objects.bulk_create(
            [
                LedgerEntry(
                    account_type=LedgerEntry.AccountType.INVENTORY,
                    amount=po_value,
                    debit=True,
                    reference_id=order.order_number,
                    related_entity=producer_id,
                    user=self.user,
                ),
                LedgerEntry(
                    account_type=LedgerEntry.AccountType.ACCOUNTS_PAYABLE,
                    amount=po_value,
                    debit=False,
                    reference_id=order.order_number,
                    related_entity=producer_id,
                    user=self.user,
                ),
            ]
        )

        input_vat = po_value * VAT_RATE
        LedgerEntry.objects.create(
            account_type=LedgerEntry.AccountType.VAT_RECEIVABLE,
            amount=input_vat,
            debit=True,
            reference_id=order.order_number,
            related_entity=producer_id,
            user=self.user,
        )

        payment_amount = po_value + input_vat
        tds_amount = Decimal("0")
        if po_value > TDS_THRESHOLD and producer.registration_number:
            tds_rate = Decimal("0.015")  # Example TDS rate
            tds_amount = po_value * tds_rate
            payment_amount -= tds_amount
            LedgerEntry.objects.create(
                account_type=LedgerEntry.AccountType.TDS_PAYABLE,
                amount=tds_amount,
                debit=False,
                reference_id=order.order_number,
                related_entity=producer_id,
                user=self.user,
            )

        LedgerEntry.objects.create(
            account_type=LedgerEntry.AccountType.ACCOUNTS_PAYABLE,
            amount=payment_amount,
            debit=True,
            reference_id=order.order_number,
            related_entity=producer_id,
            user=self.user,
        )

        AuditLog.objects.create(
            transaction_type=AuditLog.TransactionType.PROCUREMENT,
            reference_id=order.order_number,
            entity_id=producer_id,
            amount=payment_amount,
            user=self.user,
        )
        return order

    @transaction.atomic
    def sales_process(self, customer_id, product_id, quantity, selling_price):
        customer = Customer.objects.get(id=customer_id)
        product = Product.objects.get(id=product_id)
        if product.stock < quantity:
            raise ValueError("Insufficient stock")

        sales_value = Decimal(quantity) * Decimal(selling_price)
        order = Order.objects.create(
            customer=customer,
            product=product,
            quantity=quantity,
            status=Order.Status.PENDING,
            total_price=sales_value,
            user=self.user,
        )
        sale = Sale.objects.create(order=order, quantity=quantity, sale_price=selling_price, user=self.user)

        cogs = Decimal(quantity) * Decimal(product.cost_price)
        LedgerEntry.objects.bulk_create(
            [
                LedgerEntry(
                    account_type=LedgerEntry.AccountType.ACCOUNTS_RECEIVABLE,
                    amount=sales_value,
                    debit=True,
                    reference_id=order.order_number,
                    related_entity=customer_id,
                    user=self.user,
                ),
                LedgerEntry(
                    account_type=LedgerEntry.AccountType.SALES_REVENUE,
                    amount=sales_value,
                    debit=False,
                    reference_id=order.order_number,
                    related_entity=customer_id,
                    user=self.user,
                ),
                LedgerEntry(
                    account_type=LedgerEntry.AccountType.COST_OF_GOODS_SOLD,
                    amount=cogs,
                    debit=True,
                    reference_id=order.order_number,
                    related_entity=customer_id,
                    user=self.user,
                ),
                LedgerEntry(
                    account_type=LedgerEntry.AccountType.INVENTORY,
                    amount=cogs,
                    debit=False,
                    reference_id=order.order_number,
                    related_entity=customer_id,
                    user=self.user,
                ),
            ]
        )

        output_vat = sales_value * VAT_RATE
        invoice_amount = sales_value + output_vat
        LedgerEntry.objects.create(
            account_type=LedgerEntry.AccountType.VAT_PAYABLE,
            amount=output_vat,
            debit=False,
            reference_id=order.order_number,
            related_entity=customer_id,
            user=self.user,
        )

        customer.current_balance = models.F("current_balance") + invoice_amount
        customer.save()

        AuditLog.objects.create(
            transaction_type=AuditLog.TransactionType.SALES,
            reference_id=order.order_number,
            entity_id=customer_id,
            amount=invoice_amount,
            user=self.user,
        )
        return sale

    @transaction.atomic
    def reconciliation_process(self):
        vat_payable = LedgerEntry.objects.filter(account_type=LedgerEntry.AccountType.VAT_PAYABLE, user=self.user).aggregate(
            models.Sum("amount")
        )["amount__sum"] or Decimal("0")

        vat_receivable = LedgerEntry.objects.filter(
            account_type=LedgerEntry.AccountType.VAT_RECEIVABLE, user=self.user
        ).aggregate(models.Sum("amount"))["amount__sum"] or Decimal("0")

        net_vat = vat_payable - vat_receivable

        tds_total = LedgerEntry.objects.filter(account_type=LedgerEntry.AccountType.TDS_PAYABLE, user=self.user).aggregate(
            models.Sum("amount")
        )["amount__sum"] or Decimal("0")

        if tds_total > 0:
            LedgerEntry.objects.bulk_create(
                [
                    LedgerEntry(
                        account_type=LedgerEntry.AccountType.TDS_PAYABLE,
                        amount=tds_total,
                        debit=True,
                        reference_id="TDS_PAYMENT",
                        related_entity=0,
                        user=self.user,
                    ),
                    LedgerEntry(
                        account_type=LedgerEntry.AccountType.CASH,
                        amount=tds_total,
                        debit=False,
                        reference_id="TDS_PAYMENT",
                        related_entity=0,
                        user=self.user,
                    ),
                ]
            )

        sales_revenue = LedgerEntry.objects.filter(
            account_type=LedgerEntry.AccountType.SALES_REVENUE, user=self.user
        ).aggregate(models.Sum("amount"))["amount__sum"] or Decimal("0")

        cogs = LedgerEntry.objects.filter(account_type=LedgerEntry.AccountType.COST_OF_GOODS_SOLD, user=self.user).aggregate(
            models.Sum("amount")
        )["amount__sum"] or Decimal("0")

        profit = sales_revenue - cogs

        AuditLog.objects.create(
            transaction_type=AuditLog.TransactionType.RECONCILIATION,
            reference_id="PERIODIC",
            entity_id=0,
            amount=profit,
            user=self.user,
        )

        return {"net_vat": net_vat, "tds_total": tds_total, "profit": profit}
