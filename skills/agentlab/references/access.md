# How people get in

Whichever way you choose, it ends the same: someone opens the address, proves who they are, and lands in their own
agent (or picks one, if they have several). Only the people who own agents and the admins get in. With Cloudflare or
tinyauth you can also let a whole email domain sign in (`allow_domains = ["example.com"]`); they'll see "no agent
yet" until an admin gives them one.

`agentctl setup` asks which way you want and does the setup below for you. This page is for knowing what each way
means, and for the few things only you can do.

## Just you, on your own network

The plainest option for one person. Each agent's tools listen on fixed ports of the machine (T3 on
`http://my-server:7101`, and so on), and your own network decides who can reach them: your tailnet's access controls,
or simply your home LAN. There are no certificates and no sign-in page. T3 still only talks to devices you paired, and
pairing links use the same ports, so the desktop and phone apps work as usual.

It's one person only, because the ports skip the sign-in check; agentctl refuses it when several people own agents.
Make sure only your devices can reach those ports, and `doctor` will remind you which ones are open.

`agentctl setup --reach me` writes this for you. By hand it looks like this:

### Just you: plain ports on your tailnet (or LAN)

```toml
[cluster]
domain = "my-server"                    # the name you reach the machine by: tailnet or LAN name, or an IP
hub_domain = "my-server"
publish_address = "0.0.0.0"             # listen on your network; "127.0.0.1" if you only tunnel in

[auth]
mode = "tailscale"                      # on a LAN without Tailscale: "none", with hub_domain = "agentlab-hub"
admins = ["you@example.com"]

[hub]
publish = 7190                          # the dashboard: http://my-server:7190

[[agents]]
id = "work"
owner = "you@example.com"
[agents.publish]
t3 = 7101
accounts = 7102
browser = 7103
terminal = 7104
files = 7105

[[agents]]
id = "personal"
owner = "you@example.com"
[agents.publish]
t3 = 7111
accounts = 7112
browser = 7113
terminal = 7114
files = 7115
```

Moving to a shared setup later is a config change: drop the `publish` tables, choose one of the ways below, and run
`agentctl apply`.

## A group on one tailnet

Everyone is already on the same tailnet, and that's the sign-in: `tailscale serve` on the server gives HTTPS and tells
agentlab who each visitor is. Nothing is public. agentctl installs Tailscale and signs the machine in, either with an
auth key you saved (`agentctl secret set tailscale-authkey`) or by giving you a login link to open.

Two things are yours in the Tailscale admin console: turn on MagicDNS and HTTPS Certificates (DNS page), and make sure
the access controls let the agent owners reach this machine on port 443 and the dashboard's port (8443 by default).
Use people's tailnet login names as owners and admins, exactly as `tailscale status` shows them.

The desktop and phone apps just work here: they connect over the tailnet, and the person's tailnet identity picks
their agent.

## Cloudflare

People sign in at Cloudflare (a code by email, Google, Microsoft, or anything set up in Zero Trust), and a Cloudflare
tunnel brings the traffic in, so the server opens no ports. The cluster gets its own tunnel and its own Access
application; being allowed here grants nothing anywhere else in the account.

You'll need a Cloudflare API token. Create it under My Profile → API Tokens → Create Token → Custom, with:

- Account · Cloudflare One Connector: cloudflared → Edit (older accounts call it Argo Tunnel (Legacy))
- Account · Access: Apps and Policies → Edit (newer dashboards split it into Access: Apps and Access: Policies; give
  both Edit)
- Account · Access: Identity Providers → Read
- Account · Access: Organizations → Read (how agentlab learns your team name; not needed if you set
  `[auth.cloudflare] team` yourself)
- Zone · DNS → Edit, limited to your domain's zone (the plain "DNS" row, not "Zone DNS Settings")

Already made a token without one of these? Edit it in the dashboard and tick the missing row: the token keeps the same
value, so nothing on the server changes.

Save it on the server with `agentctl secret set cloudflare-api` (setup asks for it). From the token and your address,
agentlab finds the account, the zone and your Zero Trust team by itself, then creates the tunnel, the DNS records for
exactly your addresses, and the Access application allowing exactly your people. Adding a person later updates that
list on the next `apply`; no dashboard visit needed. `agentctl doctor` checks the token and names any permission it
lacks.

Sign-in methods are up to you. The code by email needs no setup at all. For one-click sign-in add Google Workspace or
Microsoft Entra ID in Zero Trust → Settings → Authentication (the redirect address is
`https://<your-team>.cloudflareaccess.com/cdn-cgi/access/callback`). If the account has a single method, agentlab uses
it straight away; with several, everyone is offered all of them unless you set `login_method` to one.

Keep every address one level under your domain (`agents.example.com`, `agents-hub.example.com`): Cloudflare's free
certificate covers only that level. For the T3 desktop and phone apps, set `pair_domain = "{id}-t3.example.com"`: each
agent then gets an address that skips the browser sign-in and only accepts devices its owner paired.

## Google sign-in on the server (tinyauth)

For when there's no Cloudflare and no tailnet: tinyauth shows a Google sign-in page on the server itself, and the
server is reachable from the internet on ports 80 and 443 (certificates come from Let's Encrypt automatically).

You'll need a Google OAuth client (Google Cloud console → Credentials → OAuth client ID, Web application) with the
redirect address `https://<sign-in address>/api/oauth/callback/google`. Save its id and secret with `agentctl secret
set tinyauth-google-id` and `agentctl secret set tinyauth-google-secret`. Point DNS records for every address (agents,
dashboard, sign-in page) at the server, and open ports 80 and 443 to it.

agentlab checks identity again behind tinyauth, and refuses tinyauth versions with known sign-in bypasses, so a bug in
tinyauth alone can't open someone else's agent.

## Testing on your own machine

`mode = "none"` lets everyone in as admin and listens only on the machine itself. It's for trying agentlab out
(`curl -H 'Host: agents.localhost' http://127.0.0.1:8088/`), never for a machine other people can reach.
