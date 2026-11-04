# shellcheck shell=bash
# /etc/profile.d/zz-agent.sh: puts the agent's tools and env back after login shells rebuild PATH.
export NPM_CONFIG_PREFIX=${HOME}/.npm-global
export PATH="${HOME}/.local/bin:${HOME}/.npm-global/bin:${PATH}"
export DISPLAY=:99
export XDG_RUNTIME_DIR=/run/user/1000
export DOCKER_HOST=unix:///run/user/1000/docker.sock
export TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/run/user/1000/dockerd.sock
export TESTCONTAINERS_HOST_OVERRIDE=localhost
[ -x /home/linuxbrew/.linuxbrew/bin/brew ] && eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
# shellcheck source=image/load-env.sh
. /etc/agent/load-env.sh
