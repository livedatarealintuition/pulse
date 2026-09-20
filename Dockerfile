# syntax=docker/dockerfile:1
#
# Pulse — self-hosted portfolio dashboard
#
#   docker build -t pulse .
#   docker run -d --name pulse -p 5000:5000 -v pulse-data:/data pulse
#
# Data (portfolio.json / watchlist.json / system_config.json) lives in the
# /data volume — it is NOT baked into the image.

FROM python:3.12-slim

WORKDIR /app

# Dependencies first so the layer caches across code edits
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# PULSE_HOME moves the JSON data files (and uploads/) to a writable location.
# The static assets the app serves (pulse.css, pulse_logo.jpg) are copied into
# that directory at start-up by the entrypoint, because the app looks for them
# under PULSE_HOME too.
ENV PULSE_HOME=/data
RUN chmod +x /app/docker-entrypoint.sh
VOLUME ["/data"]

EXPOSE 5000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# single worker on purpose: the app runs its own background price warmer
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--timeout", "120", "pulse_free:app"]
