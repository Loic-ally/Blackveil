FROM rust:1.86-slim-bookworm AS agent-build
WORKDIR /src
COPY agent/Cargo.toml agent/Cargo.lock ./
COPY agent/src ./src
RUN cargo build --release --locked

FROM rust:1.86-slim-bookworm AS indexer-build
WORKDIR /src
COPY indexer/Cargo.toml indexer/Cargo.lock ./
COPY indexer/src ./src
RUN cargo build --release --locked

FROM debian:13-slim
ARG TARGETARCH
ENV DEBIAN_FRONTEND=noninteractive
COPY images/SHA512SUMS /opt/aether/SHA512SUMS
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl cloud-image-utils openssh-client python3 qemu-utils \
      $(if [ "$TARGETARCH" = "arm64" ]; then printf '%s' 'qemu-system-arm qemu-efi-aarch64'; else printf '%s' 'qemu-system-x86 ovmf'; fi) \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home --home-dir /var/lib/aether-vm --shell /usr/sbin/nologin vmrunner \
    && mkdir -p /opt/aether /var/lib/aether-vm \
    && chown 10001:10001 /var/lib/aether-vm \
    && if [ "$TARGETARCH" = "arm64" ]; then \
         image=debian-13-genericcloud-arm64.qcow2; \
       else \
         image=debian-13-genericcloud-amd64.qcow2; \
       fi \
    && curl --fail --location --retry 3 "https://cloud.debian.org/images/cloud/trixie/latest/$image" -o /opt/aether/debian-base.qcow2 \
    && while read -r digest name; do [ "$name" != "$image" ] || printf '%s  %s\n' "$digest" /opt/aether/debian-base.qcow2; done < /opt/aether/SHA512SUMS | sha512sum --check --status \
    && if [ "$TARGETARCH" = "arm64" ]; then test -e /usr/share/AAVMF/AAVMF_CODE.fd; else test -e /usr/share/OVMF/OVMF_CODE_4M.fd; fi
COPY --from=agent-build /src/target/release/aether-agent /opt/aether/aether-agent
COPY --from=indexer-build /src/target/release/aether-indexer /opt/aether/aether-indexer
COPY render-cloud-init.py /opt/aether/render-cloud-init.py
COPY entrypoint.sh /usr/local/bin/blackveil-vm-entrypoint
RUN chmod 0755 /usr/local/bin/blackveil-vm-entrypoint /opt/aether/render-cloud-init.py /opt/aether/aether-agent /opt/aether/aether-indexer
USER 10001:10001
EXPOSE 2222 18080
ENTRYPOINT ["/usr/local/bin/blackveil-vm-entrypoint"]
