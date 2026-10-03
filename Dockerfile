FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /service
COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.txt
COPY app ./app

USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "app.start"]
