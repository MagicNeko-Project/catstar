FROM golang:alpine AS builder

WORKDIR /src/app/catstar-backup

COPY app/catstar-backup/go.mod app/catstar-backup/go.sum ./
RUN go mod download

COPY app/catstar-backup/ ./
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/catstar-backup ./cmd/catstar-backup

FROM alpine:latest

RUN apk add --no-cache openssh-client bash zsh git python3 py3-pip ansible
RUN apk add --no-cache cloudflared --repository=http://dl-cdn.alpinelinux.org/alpine/edge/testing

WORKDIR /app
COPY . /app

COPY --from=builder /out/catstar-backup /app/app/catstar-backup/bin/catstar-backup
RUN ln -s /app/app/catstar-backup/bin/catstar-backup /usr/local/bin/catstar-backup
