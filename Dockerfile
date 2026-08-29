FROM --platform=$BUILDPLATFORM golang:alpine AS builder

WORKDIR /src/app/catstar-backup

COPY app/catstar-backup/go.mod app/catstar-backup/go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download

COPY app/catstar-backup/ ./

ARG TARGETOS TARGETARCH TARGETVARIANT
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 \
    GOOS=${TARGETOS} \
    GOARCH=${TARGETARCH} \
    GOARM=${TARGETVARIANT#v} \
    go build -ldflags="-s -w" -o /out/catstar-backup ./cmd/catstar-backup

FROM alpine:latest

RUN apk add --no-cache openssh-client bash zsh git python3 py3-pip ansible
RUN apk add --no-cache cloudflared --repository=https://dl-cdn.alpinelinux.org/alpine/edge/testing

WORKDIR /app
COPY . /app

COPY --from=builder /out/catstar-backup /app/app/catstar-backup/bin/catstar-backup
RUN ln -s /app/app/catstar-backup/bin/catstar-backup /usr/local/bin/catstar-backup
