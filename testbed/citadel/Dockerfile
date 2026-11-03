FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        sudo procps libcap2-bin findutils tar coreutils \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask requests

RUN useradd -m -s /bin/bash appuser && useradd -m -s /bin/bash deploy

RUN echo 'appuser ALL=(root) NOPASSWD: /usr/bin/tar' > /etc/sudoers.d/appuser \
    && chmod 440 /etc/sudoers.d/appuser
RUN chmod u+s /usr/bin/base64

RUN mkdir -p /opt/app \
    && printf 'DB_PASSWORD=R3p0rt!ng#C1tadel\nDEPLOY_KEY=citadel-deploy-2026\n' > /opt/app/.env \
    && chown appuser:appuser /opt/app/.env
RUN echo 'FLAG{citadel_ssti_to_root_2026}' > /root/root.txt && chmod 600 /root/root.txt

COPY app.py /app/app.py
WORKDIR /app
USER appuser
EXPOSE 5000
CMD ["python", "app.py"]
