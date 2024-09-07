from rest_framework import viewsets

from .models import Producer, Customer, Product, Order, Sale
from .serializers import ProducerSerializer, CustomerSerializer, ProductSerializer, OrderSerializer, SaleSerializer


class ProducerViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing producer instances.
    """
    queryset = Producer.objects.all()
    serializer_class = ProducerSerializer


class CustomerViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing customer instances.
    """
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer


class ProductViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing product instances.
    """
    queryset = Product.objects.all()
    serializer_class = ProductSerializer


class OrderViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing order instances.
    """
    queryset = Order.objects.all()
    serializer_class = OrderSerializer


class SaleViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing sale instances.
    """
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer
