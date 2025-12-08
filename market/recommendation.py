import random
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from producer.models import MarketplaceProduct

from .models import ShoppableVideo, UserInteraction, VideoLike, VideoSave


class VideoRecommendationService:
    def __init__(self):
        pass

    def get_user_interests(self, user):
        """
        Derive user interests from their history.
        Returns a dictionary with 'categories' and 'tags'.
        """
        interests = {"categories": set(), "tags": set()}

        if not user or not user.is_authenticated:
            return interests

        # 1. From Liked Videos
        liked_videos = ShoppableVideo.objects.filter(likes__user=user).select_related("product")
        for video in liked_videos:
            if video.product.category:
                interests["categories"].add(video.product.category)
            if video.tags:
                interests["tags"].update(video.tags)

        # 2. From Saved Videos
        saved_videos = ShoppableVideo.objects.filter(saves__user=user).select_related("product")
        for video in saved_videos:
            if video.product.category:
                interests["categories"].add(video.product.category)
            if video.tags:
                interests["tags"].update(video.tags)

        # 3. From User Interactions (viewed products)
        # Assuming UserInteraction stores product_id in data
        interactions = UserInteraction.objects.filter(user=user, event_type="product_view").order_by("-created_at")[
            :50
        ]  # Last 50 interactions

        product_ids = []
        for interaction in interactions:
            if interaction.data and "product_id" in interaction.data:
                product_ids.append(interaction.data["product_id"])

        if product_ids:
            products = MarketplaceProduct.objects.filter(id__in=product_ids)
            for product in products:
                if product.category:
                    interests["categories"].add(product.category)
                # Assuming product might have tags, if not we skip
                # if product.tags: interests["tags"].update(product.tags)

        return interests

    def get_candidate_videos(self, user):
        """
        Generate candidate videos based on user interests and trends.
        """
        all_videos = ShoppableVideo.objects.filter(is_active=True).select_related("product")

        if not user or not user.is_authenticated:
            # For anonymous users, return trending videos
            return list(all_videos.order_by("-trend_score")[:50])

        interests = self.get_user_interests(user)
        candidates = set()

        # 1. Interest-based (Category)
        if interests["categories"]:
            cat_videos = all_videos.filter(product__category__in=interests["categories"])
            candidates.update(cat_videos)

        # 2. Interest-based (Tags)
        # This is harder to do efficiently in DB with JSONField list containment without specific DB functions
        # For now, we'll fetch recent videos and filter in python or use a simpler approach
        # Let's fetch top trending videos and filter them
        trending_videos = all_videos.filter(trend_score__gt=0.5).order_by("-trend_score")[:100]

        for video in trending_videos:
            candidates.add(video)
            # Also check tags match in python for these
            if any(tag in interests["tags"] for tag in video.tags):
                candidates.add(video)

        # If we don't have enough candidates, add some random recent ones
        if len(candidates) < 20:
            recent_videos = all_videos.order_by("-created_at")[:20]
            candidates.update(recent_videos)

        return list(candidates)

    def score_video(self, video, user, interests):
        """
        Score a video for a specific user.
        """
        score = 0.0

        # 1. Category Match
        if video.product.category in interests["categories"]:
            score += 2.0

        # 2. Tag Match
        tag_match_count = len(set(video.tags) & interests["tags"])
        score += 1.5 * tag_match_count

        # 3. Engagement Metrics
        # Normalize these or use log scale in real app
        # Here we use raw counts but scaled down
        score += 0.01 * video.views_count  # Proxy for watch time
        score += 1.0 * video.likes_count
        score += (
            1.2 * video.shares_count
        )  # Using shares as saves proxy if saves count not on model, but we added VideoSave model

        # We need to count saves efficiently.
        # Ideally ShoppableVideo should have saves_count field updated via signals.
        # For now, we'll query it or assume shares_count is close enough for this algo demo
        # score += 1.2 * video.saves.count() # This would be N+1 query, avoid in loop

        # 4. Trend Score
        score += 4.0 * video.trend_score

        # 5. Randomness
        score += random.uniform(0, 0.5)

        return score

    def generate_feed(self, user, feed_size=20):
        """
        Generate the final feed for the user.
        """
        candidates = self.get_candidate_videos(user)
        interests = self.get_user_interests(user)

        scored_candidates = []
        for video in candidates:
            s = self.score_video(video, user, interests)
            scored_candidates.append((video, s))

        # Rank
        ranked_candidates = sorted(scored_candidates, key=lambda x: x[1], reverse=True)

        # Return top N
        return [item[0] for item in ranked_candidates][:feed_size]
