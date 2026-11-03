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

A Cloudflare tunnel brings the traffic in, so the server opens no ports, and Cloudflare Access decides who gets in.
The cluster gets its own tunnel and its own Access application; being allowed here grants nothing anywhere else in the
account. There are two ways to set it up.

**Private (the default): only devices on your Cloudflare One client.** The addresses don't exist on the internet at
all: there are no public DNS records, and a browser that isn't on the Cloudflare One (WARP) client can't even find
them. It works like a company database reached over the client. Gateway sends the client's traffic for your addresses
over the tunnel by private hostname routes, and an Access application for those private hostnames lets in exactly
your people, signed in by their client session, so the T3 desktop and phone apps work too. Pick this when everyone
who gets an agent already runs the company's Cloudflare One client.

**Public: a sign-in page anyone can find.** Each address is a normal public hostname with Cloudflare's sign-in page in
front; anyone can reach the page, only your people get past it. Pick this when people don't all run the client. Set
`require_warp = true` too and only devices on the client get past the sign-in (the page itself stays public).

```toml
[auth.cloudflare]
network = "private"     # or "public"
https = true            # private: a real certificate (setup writes this for new installs)
```

**Private over HTTPS.** With `https = true` the addresses open as `https://agents.example.com` with the usual padlock,
and nothing is installed on anyone's device. The server gets a Let's Encrypt certificate for your addresses by
proving it controls the zone through Cloudflare DNS (the addresses are private, so Let's Encrypt couldn't reach them
otherwise); the certificate names `*.example.com`, so the public certificate log shows one wildcard rather than every
agent's address. Nothing is decrypted on the way: Gateway's TLS inspection stays off, so Access still lets each
connection in or not by who is on the client, but it can't add its signed identity to an encrypted request. So the
gate asks Access itself: agentlab creates a second application, `agentlab-<cluster> sign-in` (an OIDC application
for the same people), and the gate signs people in through it once per session (12 hours; on a device on the client
that's a few redirects with no prompt), then keeps its own encrypted cookie. Each agent's T3 desktop and phone apps
get an address of their own (`pair_domain`, which setup sets to `{id}-t3.<your zone>`): it goes straight to T3,
which only accepts devices its owner paired.

The switch is careful: setup creates the sign-in application first and keeps plain `http://` working; once the
server holds a valid certificate, the next `agentctl apply` adds port 443 to the Access application and the gate
starts redirecting `http://` to `https://`. Until then there is simply no HTTPS to see, so nobody meets a certificate
warning. `agentctl doctor` shows each step, and warns two weeks before the certificate would expire (it renews by
itself well before). `https = false` goes back to plain HTTP and removes the sign-in application.

The certificate needs a token that may edit DNS records in your zone; the API token below already can. To keep that
power off the web server, give it a separate token with only Zone · DNS → Edit and set `[cloudflare]
acme_token_file` to its file.

For private, `cloudflare setup` also turns on what your Zero Trust organization needs, through the token, only
where it's off or unset: the Gateway proxy (TCP and UDP), a Cloudflare One Client authentication session duration
(`[auth.cloudflare] client_session`, 24h by default; one already set is never changed, and "client authentication for
all applications" is never turned on), and agentlab's people policy added to device enrollment after the policies
already there, so your people can enroll the client. Client profiles in Include mode get your team domain and the
sign-in provider added to their list (nothing removed), or an expired client session can't re-authenticate. Two
things stay yours: if your client profiles use split tunnels
in Include mode, include the range Cloudflare resolves private hostnames to (`172.64.128.0/20` by default), and keep
your domain out of Local Domain Fallback.

`cloudflare setup` checks the token and these settings before it changes anything, and builds the new way in (routes
and the Access app) before it switches the tunnel and removes the old public records, so a stop halfway never locks
you out by surprise; it tells you when an earlier run already did. `agentctl doctor` checks all of it, and warns when
another application in your account admits a whole domain you allow in (anyone who can enroll the client could then
reach it).

You'll need a Cloudflare API token. Create it under My Profile → API Tokens → Create Token → Custom, with:

- Account · Cloudflare One Connector: cloudflared → Edit (older accounts call it Argo Tunnel (Legacy))
- Account · Access: Apps and Policies → Edit (newer dashboards split it into Access: Apps and Access: Policies; give
  both Edit)
- Account · Access: Identity Providers → Read
- Account · Access: Organizations → Edit (your team name, and the client session duration while it has none)
- Zone · DNS → Edit, limited to your domain's zone (the plain "DNS" row, not "Zone DNS Settings"); private uses it to
  remove any public records agentlab made earlier
- For private: Account · Cloudflare One Networks → Edit (the tunnel's hostname routes; older dashboards: Cloudflare
  Tunnel → Edit) and Account · Zero Trust → Edit (turns on the Gateway proxy when it's off)
- For `require_warp`: Account · Zero Trust → Edit (the Gateway device check, created if missing)

Already made a token without one of these? Edit it in the dashboard and tick the missing row: the token keeps the same
value, so nothing on the server changes. `agentctl doctor` checks the token and names any permission it lacks.

Save it on the server with `agentctl secret set cloudflare-api` (setup asks for it). From the token and your address,
agentlab finds the account, the zone and your Zero Trust team by itself, then creates the tunnel, its routes (private)
or DNS records (public) for exactly your addresses, and the Access application allowing exactly your people. Adding a
person later updates that list on the next `apply`; no dashboard visit needed. agentlab only ever touches what it
named `agentlab-<cluster name>`; switching from public to private removes its own public records and apps, nothing
else.

Sign-in methods are up to you. The code by email needs no setup at all. For one-click sign-in add Google Workspace or
Microsoft Entra ID in Zero Trust → Settings → Authentication (the redirect address is
`https://<your-team>.cloudflareaccess.com/cdn-cgi/access/callback`). If the account has a single method, agentlab uses
it straight away; with several, everyone is offered all of them unless you set `login_method` to one.

Keep every address one level under your domain (`agents.example.com`, `agents-hub.example.com`). Without `https`,
private addresses are plain `http://` inside the client's encrypted tunnel: that's what lets Access hand the server a
signed identity without Gateway TLS decryption, and the T3 apps connect to the main address. With public, the T3
desktop and phone apps need `pair_domain = "{id}-t3.example.com"`: each agent then gets an address that skips the
browser sign-in and only accepts devices its owner paired.

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
