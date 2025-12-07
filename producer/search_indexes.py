from haystack import indexes

from .models import MarketplaceProduct


class MarketplaceProductIndex(indexes.SearchIndex, indexes.Indexable):
    text = indexes.CharField(document=True, use_template=True)

    name = indexes.CharField(model_attr="product__name", null=True)
    description = indexes.CharField(model_attr="product__description", null=True)
    category = indexes.CharField(model_attr="product__category__name", null=True)
    subcategory = indexes.CharField(model_attr="product__subcategory__name", null=True)
    sub_subcategory = indexes.CharField(model_attr="product__sub_subcategory__name", null=True)
    is_available = indexes.BooleanField(model_attr="is_available")
    is_made_in_nepal = indexes.BooleanField(model_attr="is_made_in_nepal")

    brand = indexes.CharField(model_attr="product__brand__name", null=True)
    size = indexes.CharField(model_attr="size", null=True)
    color = indexes.CharField(model_attr="color", null=True)
    search_tags = indexes.CharField(model_attr="search_tags", null=True)

    def get_model(self):
        return MarketplaceProduct

    def prepare_search_tags(self, obj):
        if not obj.search_tags:
            return ""
        if isinstance(obj.search_tags, list):
            return " ".join(obj.search_tags)
        return str(obj.search_tags)

    # model_attr handles extracting the names; no custom prepare methods needed
