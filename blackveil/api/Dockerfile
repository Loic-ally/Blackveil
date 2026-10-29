FROM golang:1.27-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/aether ./cmd/aether

FROM alpine:3.22
RUN apk add --no-cache ca-certificates \
    && adduser -D -u 65532 -H aether \
    && mkdir -p /var/lib/aether-vm \
    && chown 10001:10001 /var/lib/aether-vm \
    && chmod 0710 /var/lib/aether-vm
COPY --from=build /out/aether /aether
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["/aether"]
