# Security

agentlab guards people's code, chats and AI logins, so security reports get priority.

## Reporting a vulnerability

**Please don't open a public issue.** Use GitHub's private reporting instead: the repository's **Security** tab →
**Report a vulnerability**. Include what you found, how to reproduce it, and what an attacker could do with it.

You'll get an acknowledgement within a few days. Once a fix is ready we'll agree on a disclosure date and credit you
in the release notes unless you'd rather stay anonymous.

## What's in scope

Anything that lets someone do more than agentlab means to allow, for example:

- reaching another person's agent, chats, files, hub pages or companion (gate, hub scoping, routing)
- getting past sign-in or spoofing an identity in any access mode
- an agent reaching shared services or the host past the firewall, or escaping its container
- an agent making the host's root services (watcher, throttle, janitor, backups) read or write files they shouldn't
- secrets leaking into logs, results, the browser or another person's view

Not in scope: the admin being able to see everything (that's by design and documented), and attacks that need root on
the host already.

## Supported versions

agentlab is early; fixes go to `main`. Run the latest `main` and `agentctl apply` to pick them up.
