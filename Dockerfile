FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -r -u 1001 app && mkdir -p /data && chown app /data
COPY --chown=app . .
USER app
ENV CC_DATABASE=/data/costcontrol.sqlite3
EXPOSE 8000
# عامل واحد مع عدة خيوط: SQLite يعمل بأمان مع كاتب واحد في نفس الوقت
CMD gunicorn -w 1 --threads 8 -b "0.0.0.0:${PORT:-8000}" --forwarded-allow-ips "*" wsgi:app
