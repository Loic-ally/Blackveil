FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends sudo procps \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask pyyaml

RUN useradd -m -s /bin/bash www

RUN mkdir -p /app && echo 'Welcome to Obscura DocHub.' > /app/welcome.txt
COPY app.py /app/app.py

RUN mkdir -p /opt/app
COPY backup.py /opt/app/backup.py
COPY runjob.sh /opt/app/runjob.sh
COPY jobs.yml /opt/app/jobs.yml
RUN chmod 755 /opt/app/runjob.sh /opt/app/backup.py \
    && chown www:www /opt/app/jobs.yml \
    && echo 'www ALL=(root) NOPASSWD: /opt/app/runjob.sh' > /etc/sudoers.d/www \
    && chmod 440 /etc/sudoers.d/www

RUN echo 'FLAG{obscura_custom_chain_to_root}' > /root/root.txt && chmod 600 /root/root.txt

WORKDIR /app
USER www
EXPOSE 5000
CMD ["python", "app.py"]
