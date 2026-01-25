import logging

from django.db.models import Q
from rest_framework import status, views
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from market.models import MarketplaceProduct
from market.serializers import MarketplaceProductSerializer, VoiceSearchInputSerializer
from market.services import AgenticSearchService, VoiceRecognitionService

logger = logging.getLogger(__name__)


class VoiceSearchView(views.APIView):
    """
    Enhanced API View for Agentic Voice Search.
    Uses AgenticSearchService to parse intent and apply hyper-personalization.
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

        # Execute Agentic Search
        page = validated_data.get("page", 1)
        page_size = validated_data.get("page_size", 20)
        products, intent, metadata = AgenticSearchService.execute_search(
            text_query, user=request.user, page=page, page_size=page_size
        )

        product_serializer = MarketplaceProductSerializer(products, many=True, context={"request": request})

        return Response(
            {
                "query": text_query,
                "intent": intent,
                "metadata": metadata,
                "count": metadata.get("total_results", 0),
                "results": product_serializer.data,
            },
            status=status.HTTP_200_OK,
        )
