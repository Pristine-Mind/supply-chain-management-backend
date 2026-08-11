# MulyaBazzar AI Models

Repository housing the AI pipeline and matchmaking algorithms for the MulyaBazzar platform.

## Architecture & Features
* **Document Ingestion (`data/ingestion.py`):** Converts supplier PDF, HTML, and Excel catalogs into structured Markdown using `markitdown`.
* **Zero-Shot Embeddings (`embeddings/`):** Generates 384-dimensional text embeddings via `all-MiniLM-L6-v2` for cold-start matches.
* **Graph Engine (`graph_engine/`):** Builds bipartite graphs using PyTorch Geometric (`TransformerConv`) for multi-hop supply chain inference.
* **API Delivery (`api/`):** Exposes lightweight FastAPI endpoints serving ranked recommendations.

## Quickstart with Docker & `uv`
```bash
# Build Docker container
docker build -t mulyabazzar-ai:latest .

# Run container
docker run -p 8000:8000 mulyabazzar-ai:latest
### `Dockerfile`
```dockerfile
FROM python:3.10-slim

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency locks
COPY pyproject.toml uv.lock ./

# Fast frozen installation
RUN uv sync --frozen --no-cache

# Copy application files
COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

### 1. Generate Mock Data
Generate synthetic users, products, interactions, and sales. You can pass CLI parameters to scale the data.
```bash
uv run python data/mock_data_generator.py --users 100 --products 500 --interactions 5000 --sales 10000

###2. Profile Sales & Interactions
uv run python profiling/sales_profiler.py

###3. Build the PyTorch Graph
uv run python -m engine.graph_builder

###4. Run AI Inference
uv run python -m engine.inference


##1. Build the Docker Image:
docker build -t mulyabazzar-ai .

##2. Run the Container:
docker run mulyabazzar-ai

