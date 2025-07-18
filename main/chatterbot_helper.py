from chatterbot.tagging import Tagger


class NullTagger(Tagger):
    def __init__(self, *args, **kwargs):
        # skip loading spaCy
        pass

    def get_tags(self, statement):
        return []
