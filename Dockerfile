FROM alpine:latest

# Install Python, pip, Ansible, and common dependencies
RUN apk add --no-cache openssh-client bash zsh git
RUN apk add --no-cache python3 py3-pip
RUN apk add --no-cache ansible

WORKDIR /app
COPY . /app
