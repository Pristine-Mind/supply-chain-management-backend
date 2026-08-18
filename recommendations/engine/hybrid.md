# Hybrid Recommendation System

This module implements a hybrid recommendation system by combining:
- collaborative filtering
- content-based filtering

The hybrid approach improves recommendation quality by leveraging the strengths of multiple recommendation techniques.

The system generates personalized business recommendations using:
- user interaction behavior
- product category similarity
- geographic compatibility
- price compatibility
- weighted recommendation scoring


# Main Function

```python
get_hybrid_recommendations(target_user, limit=20)
```

## Purpose

Generate personalized business recommendations by combining multiple recommendation approaches into a single weighted ranking system.

---

# Recommendation Sources

The hybrid recommendation engine combines recommendations from:

1. User-Based Collaborative Filtering
2. Item-Based Collaborative Filtering
3. Matrix-Factorization-Like Collaborative Filtering
4. Content-Based Filtering

---

# Imported Recommendation Modules

```python
from .collaborative import (
    item_based_cf,
    matrix_factorization_like_cf,
    user_based_cf
)

from .content_based import content_based_score
```

---

# Hybrid Recommendation Workflow

---

# Step 1 Generate Collaborative Filtering Candidates

The system first retrieves recommendation candidates from collaborative filtering methods.

## A. User-Based Collaborative Filtering

```python
ub_users = user_based_cf(target_user)
```

### Purpose
Recommend businesses based on similar user interaction patterns.

---

## B. Item-Based Collaborative Filtering

```python
ib_users = item_based_cf(target_user)
```

### Purpose
Recommend businesses based on product category similarity.

---

## C. Matrix-Factorization-Like Collaborative Filtering

```python
mf_users = matrix_factorization_like_cf(target_user)
```

### Purpose
Recommend businesses using weighted interaction vector similarity.

---

# Step 2 Merge Candidate Users

All recommended users from collaborative filtering methods are combined into a unique candidate set.

```python
candidate_ids = set()
```

---

# Step 3 Compute Content-Based Scores

Each candidate user is evaluated using the content-based recommendation module.

```python
cb_score = content_based_score(target_user, cand_user)
```

---

## Content-Based Features Used

The content-based score includes:
- category similarity
- geographic similarity
- price compatibility

---

# Step 4 Apply Hybrid Weighted Scoring

The system combines all recommendation approaches using weighted scoring.

---

## Current Hybrid Weights

| Recommendation Type | Weight |
|---------------------|---------|
| Content-Based Filtering | 0.40 |
| User-Based CF | 0.25 |
| Item-Based CF | 0.20 |
| Matrix-Factorization-Like CF | 0.15 |

---

# Hybrid Score Formula

```text
Final Score =
(Content Score × 0.40) +
(User CF × 0.25) +
(Item CF × 0.20) +
(Matrix Factorization × 0.15)
```

---

# Step 5 Rank Recommendations

Candidate users are sorted according to:
- total hybrid score
- recommendation relevance

```python
sorted(score_map.items(), key=lambda x: x[1], reverse=True)
```

---

# Step 6 Return Final Recommendations

The highest-scoring businesses are returned as final recommendations.

# Findings

The hybrid recommendation system successfully:
- combines behavioral and business similarity
- improves recommendation accuracy
- reduces weaknesses of individual recommendation methods
- generates more personalized recommendations

The system integrates:
- interaction behavior
- category similarity
- geographic proximity
- pricing compatibility
- weighted ranking

into a unified recommendation engine.
