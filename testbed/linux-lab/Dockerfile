# Intentionally vulnerable Linux lab for MetSec. Run ONLY locally / in a VM.
# Web RCE (command injection) -> foothold as 'webuser' -> sudo-misconfig privesc to root.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        sudo procps libcap2-bin findutils iputils-ping \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask

# low-priv service account with a classic sudo misconfiguration (GTFOBins: find)
RUN useradd -m -s /bin/bash webuser \
    && echo 'webuser ALL=(root) NOPASSWD: /usr/bin/find' > /etc/sudoers.d/webuser \
    && chmod 440 /etc/sudoers.d/webuser

# a root-only flag to prove escalation worked
RUN echo 'FLAG{metsec_reached_root}' > /root/root.txt && chmod 600 /root/root.txt

COPY app.py /app/app.py
WORKDIR /app
USER webuser
EXPOSE 5000
CMD ["python", "app.py"]
