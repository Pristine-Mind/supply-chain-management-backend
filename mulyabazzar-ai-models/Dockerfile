FROM python:3.11-slim
WORKDIR /app
RUN pip install uv
COPY requirements.txt .
RUN uv pip install --system -r requirements.txt
COPY . .
CMD python data/mock_data_generator.py --users 100 --products 500 --interactions 5000 --sales 10000 && \
    python profiling/sales_profiler.py && \
    python -m engine.graph_builder && \
    python -m engine.inference