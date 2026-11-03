FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        sudo procps libcap2-bin findutils iputils-ping \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask

RUN useradd -m -s /bin/bash webuser \
    && echo 'webuser ALL=(root) NOPASSWD: /usr/bin/find' > /etc/sudoers.d/webuser \
    && chmod 440 /etc/sudoers.d/webuser

RUN echo 'FLAG{watson_reached_root}' > /root/root.txt && chmod 600 /root/root.txt

COPY app.py /app/app.py
WORKDIR /app
USER webuser
EXPOSE 5000
CMD ["python", "app.py"]
