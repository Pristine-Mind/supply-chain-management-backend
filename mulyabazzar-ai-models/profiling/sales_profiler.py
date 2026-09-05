import json
import os
from collections import defaultdict


def build_sales_profiles():
    print("Running Sales & Interaction Profiler")
    print("Loading base profiles and interaction data")

    try:
        with open("data/user_profiles.json", "r") as f:
            profiles = json.load(f)
        with open("data/b2b_interactions_cache.json", "r") as f:
            b2b = json.load(f)
        with open("data/ecommerce_sales_cache.json", "r") as f:
            eco = json.load(f)
    except FileNotFoundError as e:
        print(f"Error: Missing data file - {e}")
        print("Please run data/ingestion.py and profiling/profile_builder.py first.")
        return
    metrics = defaultdict(
        lambda: {
            "b2b_orders_made": 0,
            "b2b_connections_initiated": 0,
            "b2b_views": 0,
            "ecommerce_purchases": 0,
            "ecommerce_sales": 0,
        }
    )
    for interaction in b2b:
        initiator_id = interaction.get("initiator")
        i_type = interaction.get("interaction_type")

        if i_type == "order":
            metrics[initiator_id]["b2b_orders_made"] += 1
        elif i_type == "connect":
            metrics[initiator_id]["b2b_connections_initiated"] += 1
        elif i_type == "view":
            metrics[initiator_id]["b2b_views"] += 1
    for sale in eco:
        buyer_id = sale.get("buyer")
        seller_id = sale.get("seller")

        metrics[buyer_id]["ecommerce_purchases"] += 1
        metrics[seller_id]["ecommerce_sales"] += 1
    enriched_profiles = []
    for profile in profiles:
        user_id_str = profile.get("profile_id").replace("USER_", "")
        user_id = int(user_id_str)
        user_metrics = metrics[user_id]
        enriched = {**profile, "sales_and_interactions": dict(user_metrics)}
        enriched_profiles.append(enriched)

    output_file = "data/user_profiles_enriched.json"
    with open(output_file, "w") as f:
        json.dump(enriched_profiles, f, indent=4)

    print(f"Successfully aggregated sales data for {len(enriched_profiles)} profiles!")
    print(f"Saved to: {output_file}")


if __name__ == "__main__":
    build_sales_profiles()
