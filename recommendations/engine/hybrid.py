from collections import defaultdict

from django.contrib.auth import get_user_model

from .collaborative import item_based_cf, matrix_factorization_like_cf, user_based_cf
from .content_based import content_based_score


def get_hybrid_recommendations(target_user, limit=20):
    # Get candidates from all sources
    cb_users = []  # We'll score all candidates via content-based
    ub_users = user_based_cf(target_user, limit=limit * 2)
    ib_users = item_based_cf(target_user, limit=limit * 2)
    mf_users = matrix_factorization_like_cf(target_user, limit=limit * 2)

    # Get all unique candidate user IDs
    candidate_ids = set()
    for user_list in [ub_users, ib_users, mf_users]:
        candidate_ids.update([u.id for u in user_list])

    print("Candidate IDs:", candidate_ids)
    if not candidate_ids:
        print("No candidates found.")
        return []

    # Compute content-based score for each candidate
    scored = []
    for uid in candidate_ids:
        try:
            cand_user = get_user_model().objects.get(id=uid)
            cb_score = content_based_score(target_user, cand_user)
            if cb_score > 0.2:
                scored.append((cb_score, cand_user))
        except:
            continue

    # Weighted hybrid scoring
    score_map = defaultdict(float)
    weights = {"content": 0.4, "user_cf": 0.25, "item_cf": 0.2, "mf": 0.15}

    cb_dict = {user.id: score for score, user in scored}
    ub_ids = {u.id for u in ub_users}
    ib_ids = {u.id for u in ib_users}
    mf_ids = {u.id for u in mf_users}

    for uid in candidate_ids:
        total = 0.0
        total += weights["content"] * cb_dict.get(uid, 0)
        total += weights["user_cf"] if uid in ub_ids else 0
        total += weights["item_cf"] if uid in ib_ids else 0
        total += weights["mf"] if uid in mf_ids else 0
        score_map[uid] = total

    # Sort and return
    sorted_users = sorted(score_map.items(), key=lambda x: x[1], reverse=True)
    final_users = get_user_model().objects.filter(id__in=[uid for uid, _ in sorted_users[:limit]])
    return list(final_users)
