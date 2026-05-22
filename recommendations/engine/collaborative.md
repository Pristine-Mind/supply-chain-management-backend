# Collaborative Filtering Recommendation System

This module implements collaborative filtering techniques for generating personalized business recommendations.

Collaborative filtering recommends businesses based on:
- user interaction patterns
- behavioral similarity
- shared interests between users

The system assumes that:
> users with similar interaction behavior are likely to prefer similar businesses.

---

# Implemented Recommendation Techniques

The module contains three collaborative filtering approaches:

1. User-Based Collaborative Filtering
2. Item-Based Collaborative Filtering
3. Matrix-Factorization-Like Collaborative Filtering

---

# 1. User-Based Collaborative Filtering

```python
user_based_cf(target_user, limit=30)
```

## Purpose

Recommend businesses based on similarity between users.

The system identifies users with similar interaction history and recommends businesses they interacted with.

---

## Workflow

### Step 1  Get Target User Interactions

Retrieve businesses interacted with by the target user.

```python
target_interactions
```

Example:

```text
Target User → [2, 5, 8]
```

---

### Step 2 Find Similar Users

Find users who interacted with the same businesses.

```python
co_users
```

---

### Step 3 Compute Similarity

Similarity is calculated using **Jaccard Similarity**.

## Formula

```text
Similarity = Intersection / Union
```

Example:

| User A | 1,2,3 |
|--------|--------|
| User B | 2,3,4 |

Intersection = 2

Union = 4

Similarity:

```text
2 / 4 = 0.5
```

---

### Step 4 Generate Recommendations

Businesses interacted with by similar users are recommended to the target user.

---

## Findings

- Users with similar interaction behavior often prefer similar businesses.
- Interaction overlap helps identify relevant recommendations.
- Jaccard similarity effectively measures behavioral similarity.

---

# 2. Item-Based Collaborative Filtering

```python
item_based_cf(target_user, limit=30)
```

## Purpose

Recommend businesses based on product category similarity.

Instead of comparing users directly, the system compares business/product attributes.

---

## Workflow

### Step 1 Determine Partner Business Type

The system recommends:
- distributors to retailers
- retailers to distributors

---

### Step 2 Extract Product Categories

Retrieve active product categories of the target user.

```python
category_id
```

---

### Step 3 Find Matching Businesses

Find businesses having products in similar categories.

---

## Example

Target retailer categories:

```text
Electronics
Mobiles
Accessories
```

Recommended distributor categories:

```text
Electronics
Mobiles
Laptops
```

---

## Findings

- Businesses with overlapping product categories are more compatible.
- Product category similarity improves recommendation relevance.
- Category-based matching helps business discovery.

---

# 3. Matrix-Factorization-Like Collaborative Filtering

```python
matrix_factorization_like_cf(target_user, limit=30)
```

## Purpose

Recommend businesses using weighted interaction vectors and cosine similarity.

This approach attempts to capture hidden behavioral patterns between users.

---

## Workflow

### Step 1 Create Interaction Vectors

Each user interaction is converted into weighted vectors.

Example:

| Business ID | Weight |
|-------------|---------|
| 2 | 5 |
| 7 | 3 |
| 9 | 8 |

Vector:

```text
[5, 3, 8]
```

---

### Step 2 Compute Cosine Similarity

Similarity between users is calculated using cosine similarity.

## Formula

```text
Cosine Similarity =
Dot Product / (Norm A × Norm B)
```

---

### Step 3 Score Candidate Businesses

Businesses not yet interacted with by the target user receive scores based on:
- similarity score
- interaction weight

---

### Step 4 Generate Recommendations

Top-scoring businesses are returned as recommendations.

---

## Findings

- Weighted interaction vectors capture hidden user preferences.
- Cosine similarity helps identify users with similar behavior patterns.
- Users with similar interaction strength may prefer similar businesses even without category overlap.

---

# Overall Collaborative Filtering Findings

The collaborative filtering module successfully:
- identifies behavioral similarity between users
- captures interaction-based preferences
- recommends businesses using shared interaction patterns
- improves personalization using collaborative behavior

The module combines:
- direct interaction overlap
- category similarity
- weighted interaction similarity

to generate personalized recommendations.


