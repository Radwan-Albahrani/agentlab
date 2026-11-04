# shellcheck shell=bash disable=SC2123  # setting PATH is this file's job
# Sourced by every bash (keep it plain shell): Homebrew, throttle shims first on PATH, then the owner's env vars.
case ":${PATH}:" in
  *:/home/linuxbrew/.linuxbrew/bin:*) ;;
  *) PATH="/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:${PATH}" ;;
esac
_rest='' _ifs=${IFS}
IFS=:
for _dir in ${PATH}; do [ "${_dir}" = /usr/local/lib/agent-shims ] || _rest="${_rest}${_rest:+:}${_dir}"; done
IFS=${_ifs}
PATH="/usr/local/lib/agent-shims${_rest:+:${_rest}}"
unset _rest _ifs _dir
export PATH
# shellcheck source=/dev/null  # the owner's variables, written by the Accounts page
[ -r "${HOME}/.config/agent/env" ] && { set -a; . "${HOME}/.config/agent/env"; set +a; }
true
