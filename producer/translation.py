from modeltranslation.translator import register, TranslationOptions
from producer.models import (
    Producer
)


@register(Producer)
class ProducerTranslationOptions(TranslationOptions):
    fields = ('name', 'address', 'registration_number')
