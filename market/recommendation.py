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

# --- UTILS ---


def apply_diversity_filter(candidate_ids, candidate_vectors, user_vector, lambda_val=0.6, top_n=20):
    """Maximal Marginal Relevance (MMR) - Vectorized Version."""
    if not candidate_vectors or len(candidate_ids) <= 1:
        return list(candidate_ids[:top_n])

    candidates = np.array(candidate_vectors).astype("float32")
    user_vec = np.array(user_vector).astype("float32")

    norms = np.linalg.norm(candidates, axis=1, keepdims=True)
    candidates = np.divide(candidates, norms, out=np.zeros_like(candidates), where=norms != 0)

    selected_indices = []
    remaining_indices = list(range(len(candidate_ids)))
    relevance = np.dot(candidates, user_vec)

    while len(selected_indices) < top_n and remaining_indices:
        if not selected_indices:
            idx_to_pick = np.argmax(relevance[remaining_indices])
        else:
            curr_remaining = candidates[remaining_indices]
            curr_selected = candidates[selected_indices]
            similarity_to_selected = np.dot(curr_remaining, curr_selected.T)
            novelty_penalty = np.max(similarity_to_selected, axis=1)

            mmr_scores = lambda_val * relevance[remaining_indices] - (1 - lambda_val) * novelty_penalty
            idx_to_pick = np.argmax(mmr_scores)

        actual_idx = remaining_indices.pop(idx_to_pick)
        selected_indices.append(actual_idx)

    return [candidate_ids[i] for i in selected_indices]


# --- ENGINES ---


class DiscoveryEngine:
    def __init__(self, factors=64):
        self.model = AlternatingLeastSquares(factors=factors, iterations=20, use_gpu=False)

    def train(self):
        likes = VideoLike.objects.values_list("user_id", "video_id")
        saves = VideoSave.objects.values_list("user_id", "video_id")
        views = UserInteraction.objects.filter(event_type__in=["video_view", "watch_time"]).values_list(
            "user_id", "video_id"
        )

        if not (likes or saves or views):
            return

        data_map = {}

        def aggregate(qs, weight):
            for u_id, v_id in qs:
                if u_id and v_id:
                    data_map[(u_id, v_id)] = data_map.get((u_id, v_id), 0) + weight

        aggregate(likes, 3.0)
        aggregate(saves, 5.0)
        aggregate(views, 1.0)

        u_ids, v_ids, weights = [], [], []
        for (u, v), w in data_map.items():
            u_ids.append(u)
            v_ids.append(v)
            weights.append(w)

        unique_u, unique_v = np.unique(u_ids), np.unique(v_ids)
        u_map = {uid: i for i, uid in enumerate(unique_u)}
        v_map = {vid: i for i, vid in enumerate(unique_v)}

        rows, cols = [u_map[u] for u in u_ids], [v_map[v] for v in v_ids]
        matrix = csr_matrix((weights, (rows, cols)), shape=(len(unique_u), len(unique_v)))
        self.model.fit(matrix)

        self.model.item_factors /= np.linalg.norm(self.model.item_factors, axis=-1, keepdims=True)
        self.model.user_factors /= np.linalg.norm(self.model.user_factors, axis=-1, keepdims=True)

        self._persist_embeddings(unique_u, unique_v, u_map, v_map)

    def _persist_embeddings(self, user_ids, video_ids, user_map, video_map):
        for vid in video_ids:
            factor = self.model.item_factors[video_map[vid]].tolist()
            ShoppableVideo.objects.filter(id=vid).update(embedding=factor)
        for uid in user_ids:
            factor = self.model.user_factors[user_map[uid]].tolist()
            UserProfile.objects.filter(user_id=uid).update(recommendation_embedding=factor)


class FastRetrievalService:
    def __init__(self, dimension=64):
        self.base_index = faiss.IndexHNSWFlat(dimension, 32, faiss.METRIC_INNER_PRODUCT)
        self.index = faiss.IndexIDMap(self.base_index)

    def rebuild_index(self):
        videos = ShoppableVideo.objects.filter(embedding__isnull=False, is_active=True).values_list("id", "embedding")
        if not videos:
            return
        ids, vectors = zip(*videos)
        self.index.add_with_ids(np.array(vectors).astype("float32"), np.array(ids).astype("int64"))

    def fetch_candidates(self, user_vector, k=100):
        if self.index.ntotal == 0:
            return []
        _, indices = self.index.search(np.array([user_vector]).astype("float32"), k)
        return [int(idx) for idx in indices[0] if idx != -1]


# --- MAIN SERVICE ---


class VideoRecommendationService:
    def __init__(self):
        self._ensure_index()

    def _ensure_index(self):
        global _FAISS_INDEX
        if "_FAISS_INDEX" not in globals():
            _FAISS_INDEX = FastRetrievalService()
            _FAISS_INDEX.rebuild_index()
        self.retrieval_service = _FAISS_INDEX

    def get_user_embedding(self, user):
        if not user or not user.is_authenticated:
            return None
        cache_key = f"user_emb_{user.id}"
        emb = cache.get(cache_key)
        if emb:
            return emb
        profile = UserProfile.objects.filter(user=user).values_list("recommendation_embedding", flat=True).first()
        if profile:
            cache.set(cache_key, profile, 3600)
            return profile
        return None

    def handle_video_cold_start(self, video):
        """Generates an initial embedding for a new video based on its tags."""
        if video.embedding:
            return video.embedding

        # Find other videos with similar tags that ALREADY have embeddings
        similar_videos = ShoppableVideo.objects.filter(tags__overlap=video.tags, embedding__isnull=False).values_list(
            "embedding", flat=True
        )[:10]

        if not similar_videos:
            return None  # Truly cold, will rely on trend_score

        # Average the embeddings of similar content
        avg_vec = np.mean([np.array(v) for v in similar_videos], axis=0)
        avg_vec = (avg_vec / np.linalg.norm(avg_vec)).tolist()

        video.embedding = avg_vec
        video.save(update_fields=["embedding"])
        return avg_vec

    def update_user_embedding_realtime(self, user, video_id, alpha=0.9):
        current_vec = self.get_user_embedding(user)
        video = ShoppableVideo.objects.filter(id=video_id).first()
        if not video:
            return

        # If video is new, try to generate a cold-start vector first
        video_vec = video.embedding or self.handle_video_cold_start(video)
        if not current_vec or not video_vec:
            return

        new_vec = (np.array(current_vec) * alpha) + (np.array(video_vec) * (1 - alpha))
        new_vec = (new_vec / np.linalg.norm(new_vec)).tolist()

        UserProfile.objects.filter(user=user).update(recommendation_embedding=new_vec)
        cache.set(f"user_emb_{user.id}", new_vec, 3600)

    def generate_feed(self, user, feed_size=20):
        user_vector = self.get_user_embedding(user)
        if user_vector:
            candidate_ids = self.retrieval_service.fetch_candidates(user_vector, k=100)
            candidates = ShoppableVideo.objects.filter(id__in=candidate_ids, is_active=True)
        else:
            return list(ShoppableVideo.objects.filter(is_active=True).order_by("-trend_score")[:feed_size])

        candidate_data = [(v.id, v.embedding) for v in candidates if v.embedding]
        if not candidate_data:
            return list(candidates[:feed_size])

        c_ids, c_vecs = zip(*candidate_data)
        final_ids = apply_diversity_filter(c_ids, c_vecs, user_vector, top_n=feed_size)
        video_map = {v.id: v for v in candidates}
        return [video_map[vid] for vid in final_ids if vid in video_map]

    def get_similar_videos(self, video_id, limit=10):
        """Content-based similarity using metadata overlap."""
        target = ShoppableVideo.objects.filter(pk=video_id).first()
        if not target:
            return []

        # Optimization: Filter by category first
        similar = (
            ShoppableVideo.objects.filter(Q(category=target.category) | Q(tags__overlap=target.tags), is_active=True)
            .exclude(id=target.id)
            .distinct()[:40]
        )

        results = []
        target_tags = set(target.tags or [])
        for v in similar:
            score = 5 if v.category == target.category else 0
            score += len(target_tags.intersection(set(v.tags or []))) * 2
            results.append((v, score))

        results.sort(key=lambda x: (x[1], x[0].trend_score), reverse=True)
        return [r[0] for r in results[:limit]]
