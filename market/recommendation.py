import logging
import random

import faiss
import numpy as np
from django.core.cache import cache
from django.db.models import Count, Q
from implicit.als import AlternatingLeastSquares
from scipy.sparse import csr_matrix

from user.models import UserProfile

from .models import ShoppableVideo, UserInteraction, VideoLike, VideoSave

logger = logging.getLogger(__name__)


class DiscoveryEngine:
    """Matrix Factorization (WALS) for latent factor discovery."""

    def __init__(self, factors=64):
        self.model = AlternatingLeastSquares(factors=factors, iterations=20, use_gpu=False)

    def train(self):
        """Build Sparse Matrix from interactions and train ALS model."""
        # Define weights for different interaction types
        # Likes = 3, Saves = 5, Views = 1
        interactions = []

        # We use user_id and video_id. For ALS, we usually need contiguous indices.
        # But we can use raw IDs if we handle the mapping.

        likes = VideoLike.objects.values("user_id", "video_id").annotate(weight=Count("id"))
        for l in likes:
            interactions.append((l["user_id"], l["video_id"], 3.0))

        saves = VideoSave.objects.values("user_id", "video_id").annotate(weight=Count("id"))
        for s in saves:
            interactions.append((s["user_id"], s["video_id"], 5.0))

        views = (
            UserInteraction.objects.filter(event_type__in=["video_view", "watch_time"])
            .values("user_id", "video_id")
            .annotate(weight=Count("id"))
        )
        for v in views:
            if v["user_id"] and v["video_id"]:
                interactions.append((v["user_id"], v["video_id"], 1.0))

        if not interactions:
            logger.warning("No interactions found for training DiscoveryEngine.")
            return

        user_ids, video_ids, weights = zip(*interactions)

        # Create mappings for sparse matrix indices
        unique_users = sorted(set(user_ids))
        unique_videos = sorted(set(video_ids))

        user_map = {uid: i for i, uid in enumerate(unique_users)}
        video_map = {vid: i for i, vid in enumerate(unique_videos)}

        rows = [user_map[uid] for uid in user_ids]
        cols = [video_map[vid] for vid in video_ids]

        matrix = csr_matrix((weights, (rows, cols)), shape=(len(unique_users), len(unique_videos)))
        self.model.fit(matrix)

        # Save embeddings back to models for persistence
        self._persist_embeddings(unique_users, unique_videos, user_map, video_map)

    def _persist_embeddings(self, user_ids, video_ids, user_map, video_map):
        """Save computed factors to UserProfile and ShoppableVideo."""
        # Update Videos
        for vid in video_ids:
            factor = self.model.item_factors[video_map[vid]].tolist()
            ShoppableVideo.objects.filter(id=vid).update(embedding=factor)

        # Update Users
        for uid in user_ids:
            factor = self.model.user_factors[user_map[uid]].tolist()
            UserProfile.objects.filter(user_id=uid).update(recommendation_embedding=factor)


class FastRetrievalService:
    """HNSW Vector Search (FAISS) for sub-100ms retrieval."""

    def __init__(self, dimension=64):
        # M=32 defines the number of bi-directional links in the graph
        self.index = faiss.IndexHNSWFlat(dimension, 32)
        self.id_map = {}  # Internal index to Video ID

    def rebuild_index(self):
        """Load embeddings from database and build FAISS index."""
        videos = ShoppableVideo.objects.filter(embedding__isnull=False, is_active=True).values("id", "embedding")
        if not videos:
            return

        vectors = []
        ids = []
        for v in videos:
            vectors.append(v["embedding"])
            ids.append(v["id"])

        vectors_np = np.array(vectors).astype("float32")
        self.index.add(vectors_np)

        for i, vid in enumerate(ids):
            self.id_map[i] = vid

        logger.info(f"FAISS index rebuilt with {len(ids)} videos.")

    def fetch_candidates(self, user_vector, k=100):
        """Search top-k similar videos in O(logN)."""
        if self.index.ntotal == 0:
            return []

        user_vector_np = np.array(user_vector).reshape(1, -1).astype("float32")
        distances, indices = self.index.search(user_vector_np, k)

        return [self.id_map[idx] for idx in indices[0] if idx != -1 and idx in self.id_map]


def apply_diversity_filter(candidates_with_vectors, user_vector, lambda_val=0.6, top_n=20):
    """Maximal Marginal Relevance (MMR) for diversity."""
    selected = []
    # remaining: List of (id, vector)
    remaining = [(vid, np.array(vec)) for vid, vec in candidates_with_vectors if vec]
    user_vec = np.array(user_vector)

    while len(selected) < top_n and remaining:
        best_mmr = -1e9
        best_item = None

        for item in remaining:
            vid, v_vector = item
            # Cosine similarity roughly equivalent to dot product for normalized vectors
            relevance = np.dot(user_vec, v_vector)

            # Penalty for similarity to already selected items
            novelty = max([np.dot(v_vector, s[1]) for s in selected]) if selected else 0

            mmr_score = lambda_val * relevance - (1 - lambda_val) * novelty

            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_item = item

        if best_item:
            selected.append(best_item)
            remaining.remove(best_item)
        else:
            break

    return [s[0] for s in selected]


class VideoRecommendationService:
    def __init__(self):
        self.retrieval_service = FastRetrievalService()
        # In a production app, we would persist the index or rebuild on startup.
        # For this implementation, we try to load from a singleton or rebuild.
        self._ensure_index()

    def _ensure_index(self):
        """Ensures the FAISS index is loaded."""
        # Simple singleton-like behavior for the session
        global _FAISS_INDEX
        if "_FAISS_INDEX" not in globals():
            global _FAISS_INDEX
            _FAISS_INDEX = FastRetrievalService()
            _FAISS_INDEX.rebuild_index()
        self.retrieval_service = _FAISS_INDEX

    def get_user_embedding(self, user):
        """Retrieve pre-computed embedding from UserProfile or cache."""
        if not user or not user.is_authenticated:
            return None

        # Try cache first
        cache_key = f"user_emb_{user.id}"
        emb = cache.get(cache_key)
        if emb:
            return emb

        try:
            profile = UserProfile.objects.get(user=user)
            emb = profile.recommendation_embedding
            if emb:
                cache.set(cache_key, emb, 3600)
                return emb
        except UserProfile.DoesNotExist:
            pass

        return None

    def generate_feed(self, user, feed_size=20, session_interests=None):
        """
        Two-Stage Pipeline:
        1. Retrieval: FAISS HNSW candidate generation.
        2. Ranking: MMR Diversity filtering.
        """
        user_vector = self.get_user_embedding(user)

        # 1. Retrieval Stage (Recall)
        if user_vector:
            candidate_ids = self.retrieval_service.fetch_candidates(user_vector, k=100)
            candidates = ShoppableVideo.objects.filter(id__in=candidate_ids, is_active=True)
        else:
            # Cold start / Anonymous: Fallback to trending
            candidates = list(ShoppableVideo.objects.filter(is_active=True).order_by("-trend_score")[:100])
            # Randomize in-memory to avoid Slice-Reorder error
            random.shuffle(candidates)
            return candidates[:feed_size]

        if not candidates.exists():
            return list(ShoppableVideo.objects.filter(is_active=True).order_by("-trend_score")[:feed_size])

        # 2. Ranking & Diversity Stage (Precision)
        # Prepare data for MMR
        candidate_data = []
        for v in candidates:
            if v.embedding:
                candidate_data.append((v.id, v.embedding))

        if not candidate_data:
            return list(candidates[:feed_size])

        final_ids = apply_diversity_filter(candidate_data, user_vector, top_n=feed_size)

        # Load full objects while maintaining MMR order
        video_map = {v.id: v for v in candidates}
        return [video_map[vid] for vid in final_ids if vid in video_map]

    def get_similar_videos(self, video_id, limit=10):
        """
        Find videos similar to the given video based on category and tags.
        Classic content-based filtering for 'More Like This' sections.
        """
        try:
            target = ShoppableVideo.objects.get(pk=video_id)
        except ShoppableVideo.DoesNotExist:
            return []

        # Find videos in same category or with overlapping tags
        similar = (
            ShoppableVideo.objects.filter(Q(category=target.category) | Q(tags__overlap=target.tags), is_active=True)
            .exclude(id=target.id)
            .distinct()
        )

        # Score them by overlap
        results = []
        target_tags = set(target.tags or [])

        for v in similar:
            score = 0
            if v.category == target.category:
                score += 5

            v_tags = set(v.tags or [])
            overlap = len(target_tags.intersection(v_tags))
            score += overlap * 2

            results.append((v, score))

        # Sort by overlap score and trend
        results.sort(key=lambda x: (x[1], x[0].trend_score), reverse=True)
        return [r[0] for r in results[:limit]]

    def get_social_proof_videos(self, video_id, limit=5):
        """
        'People who watched this also watched...'
        Collaborative filtering based on UserInteraction co-occurrence.
        """
        # Find users who watched this video
        users_who_watched = (
            UserInteraction.objects.filter(video_id=video_id, event_type__in=["video_view", "watch_time"])
            .values_list("user_id", flat=True)
            .distinct()
        )

        if not users_who_watched:
            return self.get_similar_videos(video_id, limit=limit)

        # Find other videos watched by these users
        other_videos = (
            UserInteraction.objects.filter(user_id__in=users_who_watched, event_type__in=["video_view", "watch_time"])
            .exclude(video_id=video_id)
            .values("video_id")
            .annotate(watch_count=Count("id"))
            .order_by("-watch_count")[:limit]
        )

        video_ids = [item["video_id"] for item in other_videos if item["video_id"]]
        if not video_ids:
            return self.get_similar_videos(video_id, limit=limit)

        return list(ShoppableVideo.objects.filter(id__in=video_ids, is_active=True))
