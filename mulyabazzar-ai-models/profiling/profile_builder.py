import json
import os

def build_user_profiles(producers_cache_file: str, output_file: str):
    print(f"Loading raw data from {producers_cache_file}...")
    
    if not os.path.exists(producers_cache_file):
        print("Error: Producers cache not found. Please run data/ingestion.py first.")
        return

    with open(producers_cache_file, "r") as f:
        producers = json.load(f)

    unique_profiles = {}
    for prod in producers:
        user = prod.get("user_details")
        if user:
            user_id = user.get("id")
            if user_id not in unique_profiles:
                unique_profiles[user_id] = {
                    "profile_id": f"USER_{user_id}",
                    "username": user.get("username"),
                    "email": user.get("email"),
                    "role": user.get("role"),
                    "business_type": user.get("business_type"),
                    "b2b_verified": user.get("b2b_verified"),
                    "has_access_to_marketplace": user.get("has_access_to_marketplace"),
                    "associated_producers": [prod.get("id")]
                }
            else:
                unique_profiles[user_id]["associated_producers"].append(prod.get("id"))
    os.makedirs("data", exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(list(unique_profiles.values()), f, indent=4)
        
    print(f"Success! Extracted {len(unique_profiles)} unique User Profiles based on their business_type.")
    print(f"Profiles saved as a distinct dataset to: {output_file}")

if __name__ == "__main__":
    print("--- Running Profiling Pipeline ---")
    build_user_profiles("data/producers_cache.json", "data/user_profiles.json")