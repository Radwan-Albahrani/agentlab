#!/bin/sh
# Build the agent image. TAG overrides the tag (default agentlab/agent:latest).
set -eu
cd "$(dirname "$0")"
docker build -t "${TAG:-agentlab/agent:latest}" .
