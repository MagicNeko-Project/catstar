FROM alpine:latest

# Install Python, pip, Ansible, and common dependencies
RUN apk add --no-cache openssh-client bash zsh git python3 py3-pip ansible
RUN apk add --no-cache cloudflared --repository=http://dl-cdn.alpinelinux.org/alpine/edge/testing

WORKDIR /app
COPY . /app
