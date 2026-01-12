FROM python:3.12-slim-bullseye as base
LABEL maintainer="Pristine Dev"
ENV PYTHONUNBUFFERED 1
WORKDIR /code
COPY pyproject.toml poetry.lock /code/
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        gdal-bin \
        libproj-dev \
        libgomp1 \
        wait-for-it \
        wkhtmltopdf \
    && pip install --upgrade --no-cache-dir pip poetry --root-user-action=ignore \
    && poetry --version \
    && poetry config virtualenvs.create false \
    && poetry install --no-root \
    && pip uninstall -y poetry virtualenv-clone virtualenv \
    && apt-get remove -y build-essential cmake libproj-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
COPY . /code/