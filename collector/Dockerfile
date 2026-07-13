FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for lxml
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . ./collector

# State persistence volume
RUN mkdir -p /app/data

RUN groupadd --gid 10001 osaf && \
    useradd --uid 10001 --gid osaf --no-create-home --shell /usr/sbin/nologin osaf && \
    chown -R osaf:osaf /app

USER 10001:10001

CMD ["python", "-m", "collector.main"]
