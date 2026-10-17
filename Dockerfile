FROM python:3.13-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    TIKTOKEN_CACHE_DIR=/app/.tiktoken

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "import tiktoken; tiktoken.get_encoding('o200k_base')"

COPY main.py ./
COPY src ./src

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

ENTRYPOINT ["python"]
CMD ["main.py"]
