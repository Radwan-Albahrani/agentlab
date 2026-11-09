# Node >= 24.22.1 carries the CA list without the distrusted emSign root (see the CA step below).
FROM node:26.13.0-bookworm

ARG DEBIAN_FRONTEND=noninteractive
ARG TTYD_VERSION=1.7.7

# Base and dev tools, gh, the browser stack, and the Android emulator's runtime libraries (SDK comes from the host).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git tmux jq ripgrep curl ca-certificates gnupg python3 python3-venv supervisor \
      openssh-client less unzip procps build-essential file \
      nano vim htop wget zip tree rsync lsof bash-completion man-db \
      iputils-ping dnsutils netcat-openbsd postgresql-client redis-tools sqlite3 \
      xvfb x11vnc novnc websockify fonts-liberation fonts-noto-color-emoji fonts-noto-cjk \
      libpulse0 libgl1 libegl1 libgbm1 libnss3 libxcomposite1 libxcursor1 libxi6 libxtst6 libxdamage1 libxrandr2 \
      libxkbfile1 libasound2 libdbus-1-3 libbsd0 \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
 && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
 && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list \
 && apt-get update && apt-get install -y --no-install-recommends gh google-chrome-stable \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL -o /usr/local/bin/ttyd "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.x86_64" \
 && chmod 755 /usr/local/bin/ttyd

# Per-agent Docker engine: root via sudo under Sysbox, rootless when unconfined (see agent-dockerd).
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker.gpg \
 && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
      > /etc/apt/sources.list.d/docker.list \
 && apt-get update && apt-get install -y --no-install-recommends \
      docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras \
      uidmap slirp4netns iptables iproute2 libcap2-bin sudo \
 && rm -rf /var/lib/apt/lists/* \
 # setuid newuidmap drops CAP_SETFCAP, which newer kernels need ("write to uid_map failed"): use file caps.
 && chmod u-s /usr/bin/newuidmap /usr/bin/newgidmap \
 && setcap cap_setuid,cap_setfcap+ep /usr/bin/newuidmap \
 && setcap cap_setgid,cap_setfcap+ep /usr/bin/newgidmap

# Distrust the compromised "emSign ECC Root CA - G3" ahead of Debian's fix (Node uses its own list, see FROM).
RUN apt-get update && apt-get -y upgrade && rm -rf /var/lib/apt/lists/* \
 && sed -i 's|^mozilla/emSign_ECC_Root_CA_-_G3.crt$|!mozilla/emSign_ECC_Root_CA_-_G3.crt|' /etc/ca-certificates.conf \
 && update-ca-certificates --fresh >/dev/null

# Agent user, rootless-Docker id ranges, docker group, sudo rule, runtime dir; interactive bash loads load-env.sh.
RUN usermod -l agent -d /home/agent -m node && groupmod -n agent node \
 && install -d -o agent -g agent /workspace /home/linuxbrew /usr/local/lib/agent-shims \
 && install -d -m 755 /etc/agent /opt/android-sdk \
 && install -d -o agent -g agent -m 700 /run/user/1000 \
 && echo 'agent:100000:65536' > /etc/subuid && echo 'agent:100000:65536' > /etc/subgid \
 && usermod -aG docker agent \
 && echo 'agent ALL=(root) NOPASSWD: /usr/local/sbin/agent-dockerd-root ""' > /etc/sudoers.d/agent-dockerd \
 && chmod 440 /etc/sudoers.d/agent-dockerd && visudo -cqf /etc/sudoers.d/agent-dockerd \
 && echo '. /etc/agent/load-env.sh' >> /etc/bash.bashrc \
 # The edge serves noVNC under /_agentlab/browser/ (prefix stripped): its websocket path must say so.
 && printf '%s\n' '<!doctype html><meta http-equiv="refresh" content="0; url=vnc.html?autoconnect=1&resize=scale&path=_agentlab/browser/websockify">' \
      > /usr/share/novnc/index.html

COPY --chmod=755 entrypoint.sh /usr/local/bin/agent-entrypoint
COPY --chmod=755 agent-config agent-terminal agent-janitor browser-idle-reaper browser-mcp-lazy chrome-on-demand \
     docker-on-demand agent-dockerd android-emulator adb companion agent-updater /usr/local/bin/
COPY --chmod=755 agent-dockerd-root /usr/local/sbin/
COPY --chmod=644 profile.sh /etc/profile.d/zz-agent.sh
COPY --chmod=644 playwright-mcp.json agent-instructions.md load-env.sh tools.sh /etc/agent/
COPY --chmod=644 supervisord.conf /etc/agent-supervisord.conf
COPY skills /etc/agent/skills
COPY accounts /opt/accounts
COPY throttle /usr/local/lib/agent-throttle
# The build context may be on a Windows drive (everything 777).
RUN chmod -R u=rwX,go=rX /opt/accounts /usr/local/lib/agent-throttle /etc/agent/skills \
 && chmod 755 /usr/local/lib/agent-throttle/shim /usr/local/lib/agent-throttle/shim-sync

USER agent
ENV HOME=/home/agent \
    DISPLAY=:99 \
    BASH_ENV=/etc/agent/load-env.sh \
    EDITOR=nano \
    VISUAL=nano \
    XDG_RUNTIME_DIR=/run/user/1000 \
    DOCKER_HOST=unix:///run/user/1000/docker.sock \
    # Ryuk must mount the engine's own socket, not the on-demand proxy
    TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/run/user/1000/dockerd.sock \
    # the engine publishes container ports on this container's localhost
    TESTCONTAINERS_HOST_OVERRIDE=localhost \
    NPM_CONFIG_PREFIX=/home/agent/.npm-global \
    # on the projects' own mount, so installs hardlink from the cache instead of copying into every worktree
    BUN_INSTALL_CACHE_DIR=/workspace/.cache/bun-install \
    NPM_CONFIG_STORE_DIR=/workspace/.cache/pnpm-store \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    ANDROID_HOME=/opt/android-sdk \
    ANDROID_AVD_HOME=/home/agent/.android/avd \
    PATH=/usr/local/lib/agent-shims:/home/agent/.local/bin:/home/agent/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/android-sdk/emulator
WORKDIR /workspace
# T3 can take minutes to install on a fresh home, hence the long start period.
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=600s --start-interval=5s \
  CMD curl -fs http://localhost:8790/health >/dev/null && curl -fs -o /dev/null http://localhost:7681/_agentlab/terminal/ \
      && curl -fs -o /dev/null http://localhost:3773/ || exit 1
ENTRYPOINT ["/usr/local/bin/agent-entrypoint"]
