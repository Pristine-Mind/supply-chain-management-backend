import random
from collections import defaultdict
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
        Derive user interests from their history with time decay.
        Returns a dictionary with 'categories' and 'tags' mapping to weights.
        """
        interests = {"categories": defaultdict(float), "tags": defaultdict(float)}

        if not user or not user.is_authenticated:
            return interests

        now = timezone.now()

        def calculate_decay_weight(created_at):
            # Weight = 1 / (days_since + 1)
            days_since = (now - created_at).days
            return 1.0 / (max(days_since, 0) + 1)

        # 1. From Liked Videos (High Weight)
        liked_videos = VideoLike.objects.filter(user=user).select_related("video", "video__product__product")
        for like in liked_videos:
            weight = calculate_decay_weight(like.created_at) * 2.0  # Base weight 2.0 for likes
            video = like.video
            if video.product.product.category:
                interests["categories"][video.product.product.category] += weight
            if video.tags:
                for tag in video.tags:
                    interests["tags"][tag] += weight

        # 2. From Saved Videos (Highest Weight)
        saved_videos = VideoSave.objects.filter(user=user).select_related("video", "video__product__product")
        for save in saved_videos:
            weight = calculate_decay_weight(save.created_at) * 3.0  # Base weight 3.0 for saves
            video = save.video
            if video.product.product.category:
                interests["categories"][video.product.product.category] += weight
            if video.tags:
                for tag in video.tags:
                    interests["tags"][tag] += weight

        # 3. From User Interactions (viewed products) (Lower Weight)
        interactions = UserInteraction.objects.filter(user=user, event_type="product_view").order_by("-created_at")[:50]

        product_ids = []
        interaction_dates = {}
        for interaction in interactions:
            if interaction.data and "product_id" in interaction.data:
                pid = interaction.data["product_id"]
                product_ids.append(pid)
                interaction_dates[pid] = interaction.created_at

        if product_ids:
            products = MarketplaceProduct.objects.filter(id__in=product_ids).select_related("product")
            for product in products:
                weight = calculate_decay_weight(interaction_dates.get(product.id, now)) * 1.0
                if product.product.category:
                    interests["categories"][product.product.category] += weight

        return interests

    def get_candidate_videos(self, user):
        """
        Generate candidate videos based on user interests and trends.
        """
        all_videos = ShoppableVideo.objects.filter(is_active=True).select_related("product__product")

        if not user or not user.is_authenticated:
            # For anonymous users, return trending videos
            return list(all_videos.order_by("-trend_score")[:50])

        interests = self.get_user_interests(user)
        candidates = set()

        # 1. Interest-based (Category)
        # Get top 3 categories by weight
        top_categories = sorted(interests["categories"].items(), key=lambda x: x[1], reverse=True)[:3]
        top_category_names = [c[0] for c in top_categories]

        if top_category_names:
            cat_videos = all_videos.filter(product__product__category__in=top_category_names)
            candidates.update(cat_videos)

        # 2. Interest-based (Tags)
        # Get top 5 tags
        top_tags = sorted(interests["tags"].items(), key=lambda x: x[1], reverse=True)[:5]
        top_tag_names = {t[0] for t in top_tags}

        # Fetch trending videos to filter by tags (optimization)
        trending_videos = all_videos.filter(trend_score__gt=0.5).order_by("-trend_score")[:100]

        for video in trending_videos:
            candidates.add(video)
            if video.tags and any(tag in top_tag_names for tag in video.tags):
                candidates.add(video)

        # If we don't have enough candidates, add some random recent ones
        if len(candidates) < 20:
            recent_videos = all_videos.order_by("-created_at")[:20]
            candidates.update(recent_videos)

        return list(candidates)

    def score_video(self, video, user, interests):
        """
        Score a video for a specific user using weighted interests.
        """
        score = 0.0

        # 1. Category Match (Weighted)
        cat_weight = interests["categories"].get(video.product.product.category, 0.0)
        if cat_weight > 0:
            score += 2.0 + (cat_weight * 0.5)  # Base score + weighted bonus

        # 2. Tag Match (Weighted)
        if video.tags:
            for tag in video.tags:
                tag_weight = interests["tags"].get(tag, 0.0)
                if tag_weight > 0:
                    score += 1.5 + (tag_weight * 0.3)

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
        Generate the final feed with diversity enforcement.
        Target Ratio: 60% Interest Match, 20% Trending, 20% Discovery
        """
        candidates = self.get_candidate_videos(user)
        interests = self.get_user_interests(user)

        scored_candidates = []
        for video in candidates:
            s = self.score_video(video, user, interests)
            scored_candidates.append((video, s))

        # Sort by score
        ranked_candidates = sorted(scored_candidates, key=lambda x: x[1], reverse=True)

        # Diversity Enforcement
        final_feed = []
        seen_ids = set()

        # 1. Top Interest Matches (60%)
        interest_count = int(feed_size * 0.6)
        for video, score in ranked_candidates:
            if len(final_feed) >= interest_count:
                break
            if video.id not in seen_ids:
                final_feed.append(video)
                seen_ids.add(video.id)

        # 2. Trending (20%) - High trend score, regardless of personalization
        trending_count = int(feed_size * 0.2)
        trending_candidates = sorted(candidates, key=lambda x: x.trend_score, reverse=True)

        added_trending = 0
        for video in trending_candidates:
            if added_trending >= trending_count:
                break
            if video.id not in seen_ids:
                final_feed.append(video)
                seen_ids.add(video.id)
                added_trending += 1

        # 3. Discovery / Random (Remaining 20%)
        remaining_candidates = [v for v in candidates if v.id not in seen_ids]
        random.shuffle(remaining_candidates)

        for video in remaining_candidates:
            if len(final_feed) >= feed_size:
                break
            final_feed.append(video)
            seen_ids.add(video.id)

        # Shuffle the final feed slightly so it's not strictly segmented
        # But keep top 3 highly relevant ones at the top
        if len(final_feed) > 3:
            top_3 = final_feed[:3]
            rest = final_feed[3:]
            random.shuffle(rest)
            final_feed = top_3 + rest

        return final_feed
