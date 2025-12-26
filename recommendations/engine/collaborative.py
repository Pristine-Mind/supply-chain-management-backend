import math
from collections import defaultdict

from django.contrib.auth import get_user_model

from producer.models import Product
from recommendations.models import BusinessInteraction
from user.models import UserProfile


def user_based_cf(target_user, limit=30):
    target_interactions = set(
        BusinessInteraction.objects.filter(business=target_user).values_list("target_business_id", flat=True)
    )
    if not target_interactions:
        return []

    co_users = (
        BusinessInteraction.objects.filter(target_business_id__in=target_interactions)
        .exclude(business=target_user)
        .values_list("business_id", flat=True)
        .distinct()
    )

    similarities = []
    for uid in co_users:
        user_interactions = set(
            BusinessInteraction.objects.filter(business_id=uid).values_list("target_business_id", flat=True)
        )
        if not user_interactions:
            continue
        inter = len(target_interactions & user_interactions)
        union = len(target_interactions | user_interactions)
        sim = inter / union if union > 0 else 0
        if sim > 0.1:
            similarities.append((sim, uid))

    similarities.sort(reverse=True)
    recommended = set()
    for sim, uid in similarities[:10]:
        recs = (
            BusinessInteraction.objects.filter(business_id=uid)
            .exclude(target_business_id__in=target_interactions)
            .values_list("target_business_id", flat=True)
        )
        recommended.update(recs)
        if len(recommended) >= limit:
            break

    return list(get_user_model().objects.filter(id__in=recommended)[:limit])


def item_based_cf(target_user, limit=30):
    partner_type = (
        UserProfile.BusinessType.DISTRIBUTOR
        if target_user.user_profile.business_type == UserProfile.BusinessType.RETAILER
        else UserProfile.BusinessType.RETAILER
    )

    cats = (
        Product.objects.filter(user=target_user, is_active=True, category__isnull=False)
        .values_list("category_id", flat=True)
        .distinct()
    )
    if not cats:
        return []

    return list(
        get_user_model()
        .objects.filter(user_profile__business_type=partner_type, product__category__in=cats, product__is_active=True)
        .exclude(id=target_user.id)
        .distinct()[:limit]
    )


def matrix_factorization_like_cf(target_user, limit=30):
    target_vec = defaultdict(float)
    for inter in BusinessInteraction.objects.filter(business=target_user):
        target_vec[inter.target_business_id] += inter.weight

    if not target_vec:
        return []

    candidate_scores = defaultdict(float)
    other_users = BusinessInteraction.objects.exclude(business=target_user).values_list("business_id", flat=True).distinct()

    for uid in other_users:
        other_vec = defaultdict(float)
        for inter in BusinessInteraction.objects.filter(business_id=uid):
            other_vec[inter.target_business_id] += inter.weight

        dot = sum(target_vec[k] * other_vec[k] for k in target_vec if k in other_vec)
        norm_t = math.sqrt(sum(v**2 for v in target_vec.values()))
        norm_o = math.sqrt(sum(v**2 for v in other_vec.values()))
        if norm_t == 0 or norm_o == 0:
            continue
        sim = dot / (norm_t * norm_o)

        for bid, w in other_vec.items():
            if bid not in target_vec:
                candidate_scores[bid] += sim * w

    sorted_candidates = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)
    return list(get_user_model().objects.filter(id__in=[bid for bid, _ in sorted_candidates[:limit]]))
