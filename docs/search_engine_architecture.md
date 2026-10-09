# Search Engine Taxonomy, Contextual Intent & Fallback Architecture

## 1. System Architecture Overview
ext
[User Search Query]
│
[Smart Query Parser] (Regex bounds, price parsing, origin filters)
│
[Dynamic Synonym & Intent Resolver]
Step 1: Internal Catalog Check (Category -> Subcategory -> Brand)
Step 2: Redis-Cached External Taxonomy (SearchTaxonomyNode)
│
[Catalog Query Execution]

Direct Catalog Hits (>0) = Return Results (fallback: "none")

Zero Hits + Canonical Category Match = Return Category Items (fallback: "brand_substitute")

Completely Unmatched Query = Return Trending Items (fallback: "trending")
│
[SearchIntentLog Pipeline] (Logs query, hits, intent, category & fallback type)
---

## 2. Database Schema & Storage

Static JSON files (`search_synonyms.json`) are backed by dedicated PostgreSQL models:

### 2.1 SearchTaxonomyNode (Intent & Synonym Rules)
Stores structured taxonomy, canonical associations, and aliases:
- `key` (`CharField`, unique): Primary slug identifier (e.g., `water`, `sports_shoes`).
- `canonical` (`CharField`): Standardized product or concept name (e.g., `Mineral Water`).
- `category` (`CharField`): Corresponding catalog category (e.g., `Food & Beverages`).
- `aliases` (`JSONField`): Array of synonyms, colloquial words, and brand names (e.g., `["bisleri", "aquafina", "pani"]`).
- `trending_suggestions` (`JSONField`): Array of related terms used for UI keyword chips.
- `is_active` (`BooleanField`): Toggle to enable/disable nodes without deleting data.

### 2.2 SearchIntentLog (Audit & Continuous Demand Learning)
Asynchronously records runtime user search events to uncover unmet demand patterns:
- `raw_query` (`CharField`): The exact search string entered by the user.
- `inferred_intent` (`CharField`, nullable): Canonical name resolved by the engine.
- `resolved_category` (`CharField`, nullable): Category resolved by the engine.
- `fallback_type` (`CharField`): One of `none`, `brand_substitute`, or `trending`.
- `hit_count` (`IntegerField`): Total matching products returned to the client.
- `applied_filters` (`JSONField`): Extracted parameters (`min_price`, `max_price`, `is_made_in_nepal`).
- `created_at` (`DateTimeField`): Automatic timestamp.

---

## 3. Core Engine Mechanics

### 3.1 Two-Tier Intent Resolution (DynamicSynonymService)
Evaluates sources in strict order:
1. **Internal Catalog Priority:** Checks internal active `Category`, `Subcategory`, and `Brand` tables. If matched (e.g., `nike`), returns `source: "internal_catalog"` immediately and skips external lookups.
2. **External Dynamic Taxonomy:** If not present internally, checks pre-indexed Redis cache (`marketplace_search_taxonomy_map`) for exact or word-boundary alias matches (e.g., `bisleri` → `source: "external_taxonomy"`).

### 3.2 Tiered Fallback Engine
- **Tier 1 (Direct Match):** Query matches products in the catalog directly (`fallback_type = "none"`).
- **Tier 2 (Brand Substitute):** An out-of-catalog brand or term is searched (e.g., `bisleri`). Resolves canonical intent (`Mineral Water` in `Food & Beverages`) and retrieves alternatives from that category.
- **Tier 3 (Trending Padding):** Completely unrecognized queries with zero catalog overlap return top trending products to prevent blank grids.

---

## 4. Periodic Data Feed & Sync Pipeline

### 4.1 Running the Sync Commands
bash

Ingest full production catalog (5.4k items)
python manage.py sync_production_catalog

Sync taxonomy nodes from JSON feed
python manage.py sync_taxonomy_nodes --file path/to/taxonomy_feed.json
---

## 5. Live Performance Benchmarks

Tested in the local container environment against the live database:

| Test Scenario | Query | Core Engine Latency | Full API Latency | Hits Returned | Fallback Type |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Direct Catalog Item** | `asus` | 15.67 ms | 62.59 ms | 3 | `none` |
| **Colloquial / Alias** | `pani` | 22.99 ms | 85.46 ms | 2 | `none` |
| **Out of Catalog Brand** | `bisleri` | 22.88 ms | 68.95 ms | 4 | `brand_substitute` |
| **Nepali Query (Filters)** | `sasto under 5000` | 16.33 ms | 226.30 ms | 184 | `trending` |
| **Unknown (Zero-Hit)** | `zzzznonexistentitem` | 31.17 ms | 199.45 ms | 184 | `trending` |

- **Average Core Search Engine Latency:** 21.81 ms (Target: <50 ms)
- **Average End-to-End API Response Time:** 128.55 ms
