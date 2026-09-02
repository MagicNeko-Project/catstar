FROM --platform=$BUILDPLATFORM docker.io/library/golang:alpine AS builder

WORKDIR /src/app/catstar-backup
COPY app/catstar-backup/go.mod app/catstar-backup/go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download

COPY app/catstar-backup/ ./
ARG TARGETOS TARGETARCH TARGETVARIANT
ARG VERSION COMMIT BUILD_DATE
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 \
    GOOS=${TARGETOS} \
    GOARCH=${TARGETARCH} \
    GOARM=${TARGETVARIANT#v} \
    go build -ldflags="-s -w -X main.version=${VERSION} -X main.gitCommit=${COMMIT} -X main.buildDate=${BUILD_DATE}" \
    -o /out/catstar-backup ./cmd/catstar-backup

FROM gcr.io/distroless/static-debian13:latest AS distroless
COPY --from=builder /out/catstar-backup /usr/local/bin/catstar-backup

FROM docker.io/library/debian:trixie-slim AS debian-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates openssh-client bash \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /out/catstar-backup /usr/local/bin/catstar-backup
WORKDIR /app
COPY . /app

FROM debian-slim AS debian
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg zsh git python3 python3-pip ansible \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg \
    && echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' > /etc/apt/sources.list.d/cloudflared.list \
    && apt-get update && apt-get install -y --no-install-recommends cloudflared \
    && rm -rf /var/lib/apt/lists/*

FROM docker.io/library/alpine:latest AS alpine-slim
RUN apk add --no-cache ca-certificates openssh-client bash
COPY --from=builder /out/catstar-backup /usr/local/bin/catstar-backup
WORKDIR /app
COPY . /app

FROM alpine-slim AS alpine
RUN apk add --no-cache zsh git python3 py3-pip ansible
RUN apk add --no-cache cloudflared --repository=https://dl-cdn.alpinelinux.org/alpine/edge/testing
