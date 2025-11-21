from haystack import indexes

from .models import MarketplaceProduct


class MarketplaceProductIndex(indexes.SearchIndex, indexes.Indexable):
    # Primary text field used for full text search. Use a template to build the document.
    text = indexes.CharField(document=True, use_template=True)

    # Individual fields for filtering/faceting
    name = indexes.CharField(model_attr="product__name", null=True)
    description = indexes.CharField(model_attr="product__description", null=True)
    # Index the category names directly from related product fields so they
    # are stored as simple strings in the index mapping.
    category = indexes.CharField(model_attr="product__category__name", null=True)
    subcategory = indexes.CharField(model_attr="product__subcategory__name", null=True)
    sub_subcategory = indexes.CharField(model_attr="product__sub_subcategory__name", null=True)
    is_available = indexes.BooleanField(model_attr="is_available")
    is_made_in_nepal = indexes.BooleanField(model_attr="is_made_in_nepal")

    def get_model(self):
        return MarketplaceProduct

    # model_attr handles extracting the names; no custom prepare methods needed
