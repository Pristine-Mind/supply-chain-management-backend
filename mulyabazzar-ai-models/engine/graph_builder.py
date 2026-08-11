import json
import torch
from torch_geometric.data import HeteroData
from sentence_transformers import SentenceTransformer
import os
from models.graph_models import NodeType, EdgeType, GraphNode, GraphEdge
from transformers import logging
import warnings

logging.set_verbosity_error()
warnings.filterwarnings("ignore")

def build_hetero_graph():
    print("Stage 1 & 2: Building PyTorch Heterogeneous Graph")

    print("Loading all-MiniLM-L6-v2 (Lightweight Text Encoder)")
    encoder = SentenceTransformer('all-MiniLM-L6-v2')
    data = HeteroData()
    print("Loading Enriched User Profiles and Products")
    with open("data/user_profiles_enriched.json", "r") as f:
        profiles = json.load(f)
    with open("data/products_cache.json", "r") as f:
        products = json.load(f)
    store_nodes = []
    synthesized_texts = []
    
    for profile in profiles:
        node_id = int(profile["profile_id"].replace("USER_", ""))
        s_v = f"Name: {profile['username']}. Role: {profile['business_type']}. Verified B2B: {profile['b2b_verified']}."

        valid_node = GraphNode(
            node_id=node_id,
            node_type=NodeType.STORE,
            raw_text_feature=s_v,
            business_role=profile['business_type']
        )
        
        store_nodes.append(valid_node)
        synthesized_texts.append(valid_node.raw_text_feature)
        
    print(f"Encoding {len(synthesized_texts)} store features into dense mathematical vectors")
    with torch.no_grad():
        node_embeddings = encoder.encode(synthesized_texts, convert_to_tensor=True)

    data[NodeType.STORE.value].x = node_embeddings
    print(f"Extracting Categories and encoding {len(products)} VProduct nodes (This may take a minute)")
    
  
    unique_categories = list(set(p['category'] for p in products))
    category_to_idx = {cat: i for i, cat in enumerate(unique_categories)}
    with torch.no_grad():
        cat_embeddings = encoder.encode(unique_categories, convert_to_tensor=True)
    data['VCategory'].x = cat_embeddings
    product_texts = [f"Name: {p['name']}. Category: {p['category']}. Price: {p['price']}" for p in products]
    with torch.no_grad():
        product_embeddings = encoder.encode(product_texts, batch_size=256, convert_to_tensor=True, show_progress_bar=True)
    data['VProduct'].x = product_embeddings

    print("Loading B2B Interactions (EAction) and mapping Product Edges")
    with open("data/b2b_interactions_cache.json", "r") as f:
        interactions = json.load(f)
    source_nodes = []
    target_nodes = []
    edge_weights = []

    for interaction in interactions:
        valid_edge = GraphEdge(
            source_id=interaction["initiator"],
            target_id=interaction["target_business"],
            source_type=NodeType.STORE,
            target_type=NodeType.STORE,
            edge_type=EdgeType.ACTION,
            weight=interaction["weight"]
        )
        
        source_nodes.append(valid_edge.source_id)
        target_nodes.append(valid_edge.target_id)
        edge_weights.append(valid_edge.weight)
        
    edge_index = torch.tensor([source_nodes, target_nodes], dtype=torch.long)
    edge_weight_tensor = torch.tensor(edge_weights, dtype=torch.float)

    data[NodeType.STORE.value, EdgeType.ACTION.value, NodeType.STORE.value].edge_index = edge_index
    data[NodeType.STORE.value, EdgeType.ACTION.value, NodeType.STORE.value].edge_attr = edge_weight_tensor
    src_offers, dst_offers = [], []
    for idx, prod in enumerate(products):
        src_offers.append(prod["seller_id"])
        dst_offers.append(idx)
        
    data[NodeType.STORE.value, 'EOffers', 'VProduct'].edge_index = torch.tensor([src_offers, dst_offers], dtype=torch.long)
    src_cat, dst_cat = [], []
    for idx, prod in enumerate(products):
        src_cat.append(idx)
        dst_cat.append(category_to_idx[prod["category"]])
        
    data['VProduct', 'ECategorized', 'VCategory'].edge_index = torch.tensor([src_cat, dst_cat], dtype=torch.long)

    print("\n Graph Construction Complete")
    print(data)
    os.makedirs("engine/compiled_graphs", exist_ok=True)
    torch.save(data, "engine/compiled_graphs/b2b_hetero_graph.pt")
    print("Graph saved to engine/compiled_graphs/b2b_hetero_graph.pt")

if __name__ == "__main__":
    build_hetero_graph()