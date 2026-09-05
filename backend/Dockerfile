FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      fonts-dejavu-core \
      libffi-dev \
      libcairo2 \
      libfribidi-dev \
      libgdk-pixbuf-2.0-0 \
      libgmp-dev \
      libharfbuzz-dev \
      libpango-1.0-0 \
      libpangoft2-1.0-0 \
      shared-mime-info \
    && apt-get clean \
    && find /var/lib/apt/lists -mindepth 1 -delete

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .

RUN SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
    STORAGE_BACKEND=local \
    python manage.py collectstatic --noinput \
    && test -f staticfiles/admin/css/base.css

RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /usr/src/app/media /usr/src/app/private-media \
    && chown -R appuser:appuser /usr/src/app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "ledova_backend.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
