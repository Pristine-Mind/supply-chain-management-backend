import math

from django.contrib.gis.geos import Point
from django.db.models import Max, Min

from producer.models import Product
from user.models import UserProfile


def content_based_score(target_user, candidate_user):
    weights = {"category": 0.5, "geo": 0.3, "price": 0.2}
    score = 0.0

    # --- 1. Category Overlap (Jaccard) ---
    target_cats = set(
        Product.objects.filter(user=target_user, is_active=True, category__isnull=False).values_list(
            "category_id", flat=True
        )
    )
    print("Target Categories:", target_cats)
    cand_cats = set(
        Product.objects.filter(user=candidate_user, is_active=True, category__isnull=False).values_list(
            "category_id", flat=True
        )
    )
    print("Candidate Categories:", cand_cats)
    cat_score = 0.0
    if target_cats and cand_cats:
        intersection = len(target_cats & cand_cats)
        union = len(target_cats | cand_cats)
        cat_sync = intersection / union if union > 0 else 0.0
        cat_score = cat_sync

    # --- 2. Geographic Score ---
    geo_score = 0.1
    try:
        t_prof = target_user.user_profile
        c_prof = candidate_user.user_profile
        if t_prof.location_id and c_prof.location_id:
            geo_score = 1.0 if t_prof.location_id == c_prof.location_id else 0.3
        elif all(getattr(p, "latitude") and getattr(p, "longitude") for p in [t_prof, c_prof]):
            t_point = Point(t_prof.longitude, t_prof.latitude, srid=4326)
            c_point = Point(c_prof.longitude, c_prof.latitude, srid=4326)
            dist_km = t_point.distance(c_point) * 111.32
            geo_score = max(0, 1 - (dist_km / 500))
    except:
        pass

    # --- 3. Price Compatibility ---
    price_score = 0.5
    try:
        t_prices = Product.objects.filter(user=target_user, is_active=True).aggregate(min_p=Min("price"), max_p=Max("price"))
        c_prices = Product.objects.filter(user=candidate_user, is_active=True).aggregate(
            min_p=Min("price"), max_p=Max("price")
        )
        if all(v is not None for v in [t_prices["min_p"], t_prices["max_p"], c_prices["min_p"], c_prices["max_p"]]):
            overlap = max(0, min(t_prices["max_p"], c_prices["max_p"]) - max(t_prices["min_p"], c_prices["min_p"]))
            union = max(t_prices["max_p"], c_prices["max_p"]) - min(t_prices["min_p"], c_prices["min_p"])
            price_score = overlap / union if union > 0 else 0.0
    except:
        pass

    score = weights["category"] * cat_score + weights["geo"] * geo_score + weights["price"] * price_score
    return min(1.0, max(0.0, score))
