# shellcheck shell=bash disable=SC2123  # setting PATH is this file's job
# Sourced by every bash (BASH_ENV, /etc/profile.d/zz-agent.sh, bash.bashrc, and last in ~/.profile): Homebrew on PATH,
# the throttle shims first of all (heavy jobs queue for memory and disk: /usr/local/lib/agent-throttle; a tool folder
# ahead of them, like ~/.local/bin from ~/.profile, would let builds bypass it), then the profile's env vars from the
# Accounts page. Plain shell only: this runs before every command.
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
