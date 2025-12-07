import logging

from django.db.models import Q
from rest_framework import status, views
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from market.models import MarketplaceProduct
from market.serializers import MarketplaceProductSerializer, VoiceSearchInputSerializer
from market.services import VoiceRecognitionService

logger = logging.getLogger(__name__)


class VoiceSearchView(views.APIView):
    """
    API View to handle voice search.
    Supports both client-side (text query) and server-side (audio file) processing.
    """

    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def post(self, request, *args, **kwargs):
        serializer = VoiceSearchInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        audio_file = validated_data.get("audio_file")
        text_query = validated_data.get("query")

        if audio_file:
            try:
                text_query = VoiceRecognitionService.transcribe_audio(audio_file)
                logger.info(f"Transcribed voice query: {text_query}")
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except ConnectionError as e:
                return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # Perform search
        products = MarketplaceProduct.objects.filter(
            Q(name__icontains=text_query) | Q(description__icontains=text_query)
        ).distinct()

        product_serializer = MarketplaceProductSerializer(products, many=True, context={"request": request})

        return Response(
            {"query": text_query, "count": products.count(), "results": product_serializer.data}, status=status.HTTP_200_OK
        )
