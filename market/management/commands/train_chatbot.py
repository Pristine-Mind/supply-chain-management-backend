from django.core.management.base import BaseCommand
from chatterbot import ChatBot
from chatterbot.trainers import ListTrainer, ChatterBotCorpusTrainer
from django.conf import settings


class Command(BaseCommand):
    help = "Train the chatbot with custom conversations"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting chatbot training..."))

        try:
            # Initialize chatbot
            chatterbot_settings = settings.CHATTERBOT.copy()
            chatterbot_settings["tagger_language"] = None
            bot = ChatBot(**chatterbot_settings)

            # Initialize trainers
            list_trainer = ListTrainer(bot)
            corpus_trainer = ChatterBotCorpusTrainer(bot)

            # Train on English corpus
            self.stdout.write("Training on English corpus...")
            corpus_trainer.train("chatterbot.corpus.english")

            # Train on custom conversations
            self.stdout.write("Training on custom conversations...")
            conversations = [
                # Greetings
                "Hey there!",
                "Hi! Welcome to Mulya Bazzar. What can I help you find today?",
                "Good morning",
                "Good morning ☀️! Looking for something special today?",
                "Hello",
                "Hello! Feel free to ask me about products, orders, or deals.",
                # Browsing & recommendation
                "I'm looking for organic rice",
                "We have Kathmandu Organic Rice and Pokhara Premium Rice. Do you have a preferred brand or budget?",
                "What's the best selling spice this week?",
                "Our top seller is Cumin, closely followed by Turmeric. Both are fresh from local farms!",
                "Recommend me a gift basket",
                "Our curated gift baskets include a mix of tea, herbs, and dry fruits. Would you like one under NPR 1500 or NPR 3000?",
                # Pricing & discounts
                "Do you have any discounts?",
                "Yes! We're running 10% off all grains & cereals today. Just add them to your cart to see the discounted price.",
                "How much for 5 kg of Local Rice?",
                "5 kg of Local Rice is NPR 480 (after 5% loyalty discount). Want me to add that to your cart?",
                # Order status
                "Where's my order?",
                "Can you share your order number? I'll check the latest status for you.",
                "Order #MBZ12345",
                "Order #MBZ12345 is out for delivery and should reach you by 6 PM today 🚚.",
                # Shipping & returns
                "What's your shipping charge?",
                "We offer free shipping on orders above NPR 1000. Otherwise it's NPR 50 flat-rate.",
                "Can I return an item?",
                "Yes—returns are accepted within 7 days of delivery. Just ship it back in original packaging.",
                # Small talk & sign-off
                "Thanks for your help!",
                "My pleasure! Let me know if you need anything else 😊.",
                "Bye",
                "Goodbye! Come back soon to Mulya Bazzar.",
            ]

            # Train on custom conversations
            for i in range(0, len(conversations), 2):
                list_trainer.train([conversations[i], conversations[i + 1]])

            self.stdout.write(self.style.SUCCESS("Successfully trained the chatbot!"))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error during training: {str(e)}"))
            raise
