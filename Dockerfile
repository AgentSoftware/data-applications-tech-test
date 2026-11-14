# The pipeline image. The sample snapshot is copied in, so a run needs nothing but a database.
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . && rm -rf src
COPY data ./data

USER 10001
ENTRYPOINT ["python", "-m", "psc_pipeline"]
CMD ["--input", "/app/data/persons-with-significant-control-snapshot-2026-10-29-sample.txt.gz"]
