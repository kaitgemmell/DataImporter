FROM library/python:3.11-bookworm
ARG USER=vscode
ARG DEBIAN_FRONTEND=noninteractive

# Install system dependencies including tools needed for Claude Code
RUN apt update \
    && apt install -y --no-install-recommends \
        sudo \
        git \
        ripgrep \
        jq \
        curl \
    && apt autoremove -y \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /usr/bin/bash ${USER} \
    && echo "${USER} ALL=(ALL) NOPASSWD: ALL" >/etc/sudoers.d/${USER} \
    && chmod 0440 /etc/sudoers.d/${USER}