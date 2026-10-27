# Citadel — a multi-stage pentest box for MetSec. INTENTIONALLY VULNERABLE.
# SQLi auth bypass -> admin SSTI RCE -> foothold as appuser -> sudo tar (GTFOBins) -> root.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        sudo procps libcap2-bin findutils tar coreutils \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask requests

RUN useradd -m -s /bin/bash appuser && useradd -m -s /bin/bash deploy

# Privesc path: appuser may run tar as root (GTFOBins tar --checkpoint-action) -> root shell
RUN echo 'appuser ALL=(root) NOPASSWD: /usr/bin/tar' > /etc/sudoers.d/appuser \
    && chmod 440 /etc/sudoers.d/appuser
# Alternate/decoy: SUID base64 (GTFOBins file-read — reads root files, no shell)
RUN chmod u+s /usr/bin/base64

# Lootable secrets + root flag
RUN mkdir -p /opt/app \
    && printf 'DB_PASSWORD=R3p0rt!ng#C1tadel\nDEPLOY_KEY=citadel-deploy-2026\n' > /opt/app/.env \
    && chown appuser:appuser /opt/app/.env
RUN echo 'FLAG{citadel_ssti_to_root_2026}' > /root/root.txt && chmod 600 /root/root.txt

COPY app.py /app/app.py
WORKDIR /app
USER appuser
EXPOSE 5000
CMD ["python", "app.py"]
