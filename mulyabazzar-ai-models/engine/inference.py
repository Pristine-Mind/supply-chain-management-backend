import torch
import json
import random
import torch.nn.functional as F

def random_walk_with_restart(transition_matrix, start_idx, restart_prob=0.15, max_iter=20, tol=1e-6):
    num_nodes = transition_matrix.shape[0]
    p0 = torch.zeros(num_nodes)
    p0[start_idx] = 1.0
    
    p = p0.clone()
    for _ in range(max_iter):
        p_next = (1 - restart_prob) * torch.matmul(transition_matrix, p) + restart_prob * p0
        if torch.norm(p_next - p, p=1) < tol:
            break
        p = p_next
    return p

def get_hybrid_recommendations(user_id: int, target_location: str = "Kathmandu"):
    target_profile_id = f"USER_{user_id}"
    print(f"Running NeurIPS-Aligned Hybrid Inference for {target_profile_id}")
    
    try:
        data = torch.load("engine/compiled_graphs/b2b_hetero_graph.pt", weights_only=False)
        with open("data/user_profiles_enriched.json", "r") as f:
            profiles = json.load(f)
    except FileNotFoundError:
        print("Error: Files not found. Run graph_builder.py first.")
        return []
    
    target_idx = next((i for i, p in enumerate(profiles) if p["profile_id"] == target_profile_id), None)
    if target_idx is None: 
        print(f"User {target_profile_id} not found.")
        return

    num_stores = len(profiles)
    target_internal_id = user_id
    # Algorithm A: Jaccard 
   
    user_neighbors = {int(p["profile_id"].replace("USER_", "")): set(["active" if p.get("sales_and_interactions", {}).get("b2b_orders_made", 0) > 0 else "inactive"]) for p in profiles}
    
    
    # Algorithm B: Continuous Cosine Similarity 
    store_vectors = data['VStore'].x
    target_vector = store_vectors[target_idx].unsqueeze(0)
    cosine_scores = F.cosine_similarity(target_vector, store_vectors)

    # Algorithm C: Latent Link Prediction (RWR)

    adjacency = torch.zeros((num_stores, num_stores))
    edge_index = data['VStore', 'EAction', 'VStore'].edge_index
    edge_weights = data['VStore', 'EAction', 'VStore'].edge_attr
    
    if edge_index is not None:
        for i in range(edge_index.shape[1]):
            src, dst = edge_index[0, i].item(), edge_index[1, i].item()
            adjacency[src, dst] += edge_weights[i].item()
            adjacency[dst, src] += edge_weights[i].item() 

    row_sums = adjacency.sum(dim=1, keepdim=True)
    row_sums[row_sums == 0] = 1.0
    transition_matrix = adjacency / row_sums

    rwr_scores = random_walk_with_restart(transition_matrix, start_idx=target_internal_id, restart_prob=0.15)


    # Final Stage: Weighted Hybrid Scoring S(u,v)

    w1, w2, w3 = 0.2, 0.4, 0.4 
    final_rankings = []

    for i, profile in enumerate(profiles):
        if i == target_idx: continue
            
        p_id = int(profile["profile_id"].replace("USER_", ""))
        tn = user_neighbors.get(target_internal_id, set())
        cn = user_neighbors.get(p_id, set())
        union = len(tn.union(cn))
        sim_jaccard = (len(tn.intersection(cn)) / union) if union > 0 else 0.0

        sim_cosine = cosine_scores[i].item()
        sim_rwr = rwr_scores[p_id].item()
        mock_loc = random.choice(["Kathmandu", "Pokhara", "Chitwan"])
        mock_price = random.uniform(500, 5000)
        loc_boost = 0.1 if mock_loc == target_location else 0.0
        price_penalty = (mock_price / 5000.0) * 0.15
        final_score = (w1 * sim_jaccard) + (w2 * sim_cosine) + (w3 * sim_rwr) + loc_boost - price_penalty
        
        final_rankings.append({
            "name": profile["username"],
            "type": profile["business_type"].upper(),
            "score": final_score,
            "loc": mock_loc,
            "price": mock_price
        })

    final_rankings.sort(key=lambda x: x["score"], reverse=True)
    return final_rankings

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run AI Inference for a specific user")
    parser.add_argument("--user", type=int, default=50, help="Target user ID (integer)")
    parser.add_argument("--loc", type=str, default="Kathmandu", help="Target location for boost")
    
    args = parser.parse_args()
    results = get_hybrid_recommendations(args.user, target_location=args.loc)
    print(f"Generated {len(results)} total matches. Top 5:")
    for r in results[:5]:
        print(r)