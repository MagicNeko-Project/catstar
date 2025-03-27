FROM alpine:latest

# Install Python, pip, Ansible, and common dependencies
RUN apk add --no-cache python3 py3-pip ansible bash git

WORKDIR /app
COPY . /app
