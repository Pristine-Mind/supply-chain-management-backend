# Content-Based Recommendation System

This module implements a content-based recommendation system for generating personalized business recommendations.

Content-based filtering recommends businesses by comparing business attributes instead of relying only on user interaction history.

The system generates recommendations using:
- product category similarity
- geographic proximity
- price compatibility

The recommendation engine assumes that:
> businesses with similar characteristics are more likely to be compatible.

# Main Function

```python
content_based_score(target_user, candidate_user)
```

## Purpose

Calculate a compatibility score between two businesses using multiple business attributes.

The final score is generated using weighted similarity scoring.

---

# Implemented Features

The content-based recommendation system uses three major features:

1. Category Similarity
2. Geographic Similarity
3. Price Compatibility

---

# 1. Category Similarity

## Purpose

Measure similarity between businesses based on product categories.

Businesses with overlapping product categories are considered more relevant to each other.

---

## Workflow

### Step 1 Extract Product Categories

Retrieve active product categories for:
- target user
- candidate user

```python
category_id
```

---

### Step 2 Compute Category Overlap

Category similarity is calculated using **Jaccard Similarity**.

## Formula

```text
Similarity = Intersection / Union
```

Example:

| Target Categories | Electronics, Mobiles |
|-------------------|----------------------|
| Candidate Categories | Mobiles, Accessories |

Intersection:

```text
Mobiles = 1
```

Union:

```text
Electronics, Mobiles, Accessories = 3
```

Similarity:

```text
1 / 3 = 0.33
```

---

## Findings

- Businesses with similar product categories are more likely to match.
- Category overlap improves recommendation relevance.
- Product similarity helps identify compatible business partners.

---

# 2. Geographic Similarity

## Purpose

Measure geographic compatibility between businesses.

Nearby businesses are generally better for:
- logistics
- communication
- supply chain efficiency

---

## Workflow

### Step 1 Compare Locations

If both businesses share the same location:

```python
geo_score = 1.0
```

Otherwise:

```python
geo_score = 0.3
```

---

### Step 2 Distance-Based Calculation

If latitude and longitude exist:
- GIS points are created
- distance between businesses is calculated

```python
Point(longitude, latitude, srid=4326)
```

Distance is converted into kilometers.

---

## Geographic Scoring

The score decreases as distance increases.

Example:

| Distance | Score |
|----------|--------|
| Very Near | High |
| Very Far | Low |

---

## Findings

- Geographic proximity improves business compatibility.
- Nearby businesses are more likely to collaborate efficiently.
- Location-aware recommendations improve practicality.

---

# 3. Price Compatibility

## Purpose

Compare price ranges between businesses.

Businesses operating within similar price ranges are considered more compatible.

---

## Workflow

### Step 1 Extract Price Ranges

Retrieve:
- minimum price
- maximum price

for both businesses.

---

### Step 2 Compute Price Overlap

The overlap between price ranges is calculated.

Example:

| Business A | 100 – 500 |
|------------|------------|
| Business B | 200 – 450 |

Overlap:

```text
200 – 450
```

Greater overlap results in higher compatibility.

---

## Findings

- Businesses operating in similar market ranges are more compatible.
- Price compatibility improves market alignment.
- Similar pricing structures increase recommendation quality.

---

# Final Scoring System

The final content-based recommendation score uses weighted scoring.

| Feature | Weight |
|----------|---------|
| Category Similarity | 0.5 |
| Geographic Similarity | 0.3 |
| Price Compatibility | 0.2 |

---

# Final Score Formula

```text
Final Score =
(Category Score × 0.5) +
(Geographic Score × 0.3) +
(Price Score × 0.2)
```

The final score is normalized between:

```text
0.0 → 1.0
```

---

# Overall Findings

The content-based recommendation system successfully:
- compares business characteristics
- identifies compatible business partners
- improves recommendation relevance
- supports business matchmaking

The system combines:
- category overlap
- geographic compatibility
- pricing compatibility

to generate personalized recommendations.
