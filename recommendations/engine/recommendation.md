# Hybrid Recommendation System 

This project implements a Hybrid Recommendation System for business matchmaking between retailers and distributors.


## Goals
- Produce personalized business recommendations for a given retailer (or distributor).
- Balance behavioral signals, business attributes, and contextual constraints (geography, price).
- Be explainable, testable, and performant at scale.

## Overview of Components
- `collaborative.py`: user-based, item-based, and matrix-factorization-like collaborative methods.
- `content_based.py`: attribute matching (category, geography, price), text/metadata similarity.
- `hybrid.py`: candidate generation, score normalization, weighted aggregation, reranking and filtering.
- Data pipeline: ingestion -> preprocessing -> feature store -> scoring service -> API layer.

## Data Inputs
- Interaction logs: views, inquiries, messages, orders, timestamps, interaction types and weights.
- Business metadata: categories, tags, geolocation (lat/lon), price ranges, catalog size, ratings.
- Session/context: current search terms, filters (category, region), requestor profile.
- External signals: popularity, seasonal boosts, SLA/availability flags.

## Preprocessing & Feature Engineering
- Normalize categories (canonical taxonomy) and tag vectors.
- Build interaction matrix: sparse user x business matrix with weighted events.
- Compute aggregated features: business popularity, recency-weighted interaction counts, price quantiles.
- Geospatial index: store businesses in an R-tree or PostGIS for radius queries and kNN.

## Collaborative Filtering

API (conceptual):

```python
def user_based_cf(user_id: int, k: int = 100, top_n: int = 20) -> List[Tuple[business_id, score]]:
	"""Return top `top_n` candidate businesses for `user_id` with scores."""

def item_based_cf(user_id: int, k: int = 100, top_n: int = 20) -> List[Tuple[business_id, score]]:
	"""Use item similarity (category/product overlap) to score candidates."""

def matrix_factorization_like_cf(user_id: int, model, top_n: int = 20) -> List[Tuple[business_id, score]]:
	"""Use precomputed embeddings or factorization to produce scores."""
```

Algorithms and formulas:
- Jaccard similarity for binary interaction overlap: $J(A,B)=|A\cap B|/|A\cup B|$.
- Cosine similarity for weighted vectors: $\cos(\mathbf{u},\mathbf{v}) = \frac{\mathbf{u}\cdot\mathbf{v}}{\|\mathbf{u}\|\|\mathbf{v}\|}$.
- Use MinHash + LSH for approximate Jaccard at large scale.
- For embeddings: use approximate nearest neighbor (ANN) index (e.g., Faiss, Annoy) to retrieve top candidates.

Practical details:
- Weight interaction types (order > inquiry > view). Example weights: order=3.0, inquiry=1.0, view=0.2.
- Apply time decay: weight = exp(-lambda * age_days) to prioritize recent interactions.

## Content-Based Filtering

API (conceptual):

```python
def content_score(target_business: dict, candidate: dict) -> float:
	"""Compute weighted content similarity score between two business metadata dicts."""
```

Feature components and scoring:
- Category overlap: Jaccard or TF-IDF on category/tag vectors.
- Text similarity: cosine similarity on TF-IDF or sentence embeddings of descriptions.
- Geographic proximity: convert lat/lon to haversine distance and map to score using a kernel, e.g. score_geo = exp(-dist / sigma).
- Price compatibility: normalized overlap between [min_price, max_price] ranges or percent difference threshold.

Example content score (normalized 0..1):
score = w_cat * cat_score + w_text * text_score + w_geo * geo_score + w_price * price_score

Default weights: w_cat=0.45, w_text=0.15, w_geo=0.25, w_price=0.15 (tuneable).

## Hybrid Engine

Responsibilities:
- Candidate generation: union of top-K from collaborative methods and content-based neighbors.
- Score normalization: convert each source's raw scores into comparable [0,1] range using min-max or z-score with clipping.
- Weighted aggregation: final_score = sum_i alpha_i * normalized_score_i.
- Reranking: apply business constraints, diversity heuristics, and business rules (blacklists, active flag).

Default aggregation weights (example):
- content_based: 0.40
- user_based_cf: 0.25
- item_based_cf: 0.20
- mf_like_cf: 0.15

Normalization example (min-max):
norm = (score - min_source_score) / (max_source_score - min_source_score + eps)

Final pipeline pseudo-code:

```text
candidates = union(user_based_cf(...), item_based_cf(...), matrix_cf(...), content_neighbors(...))
for c in candidates:
	s_cb = normalized(content_score(target, c))
	s_ub = normalized(user_based_score(c))
	s_ib = normalized(item_based_score(c))
	s_mf = normalized(mf_score(c))
	final = w_cb*s_cb + w_ub*s_ub + w_ib*s_ib + w_mf*s_mf
	apply_business_rules(c, final)
return topN(sorted by final)
```

## Explainability
- Return per-source contribution for each recommended business so the frontend can display "because of category match" or "similar businesses liked by peers".
- Example returned structure:

```json
{ "business_id": 123, "score": 0.87, "reasons": [{"source": "content", "contribution": 0.45, "note": "category match"}, ...] }
```

## Evaluation & Metrics
- Offline metrics: Precision@K, Recall@K, MAP@K, NDCG@K, Hit Rate, MRR.
- A/B testing metrics: conversion rate, inquiry rate, CTR on recommendations, incremental GMV.
- Offline validation: use temporal train/test splits (train on t0..tN, test on tN+1..tM) to avoid leakage.

Suggested evaluation workflow:
- Holdout 7-14 days of interactions for validation.
- Compute metrics per-user cohort (cold, warm, super-user) and per-region.


## Configurations & Hyperparameters
- source_weights: {"content":0.4, "user":0.25, "item":0.2, "mf":0.15}
- interaction_weights: {"order":3.0, "inquiry":1.0, "view":0.2}
- time_decay_lambda: 0.01
- top_k_per_source: 100

## Example Usage

```python
from recommendations.engine.hybrid import recommend_for_user

recs = recommend_for_user(user_id=42, top_n=10, filters={"region":"Bengaluru"})
for r in recs:
	print(r["business_id"], r["score"], r.get("reasons"))
```

## File Mapping (where to implement)
- `recommendations/engine/collaborative.py` — CF implementations, similarity helpers.
- `recommendations/engine/content_based.py` — attribute scoring helpers, text/geo/price functions.
- `recommendations/engine/hybrid.py` — orchestration, normalization, aggregation, API endpoint.


