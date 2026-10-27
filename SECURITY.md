# Security policy

cloudflare-notifier handles Cloudflare API credentials and security event data, so we take vulnerabilities seriously.

## Supported versions

| Package | Version | Supported |
|---|---|---|
| `@maggidev/cloudflare-notifier` (npm) | latest release | ✅ |
| `@maggidev/cloudflare-notifier` (npm) | older releases | ❌ upgrade to the latest |
| `cloudflare-notifier` (Python) | `main` branch | ✅ |

Fixes are released as a new version. They are not backported to older versions.

## Reporting a vulnerability

**Please do not open a public issue, discussion or pull request for security problems.**

Report privately through GitHub instead:

1. Go to the repository's [**Security** tab](https://github.com/N0tMaggi/CloudFlareNotifier/security).
2. Click **Report a vulnerability**.
3. Describe the issue, how to reproduce it, and the impact you expect.

Include the affected package and version. Never include real API tokens; if you exposed one while testing, revoke it in the Cloudflare dashboard.

### What to expect

- Confirmation that we received your report within **7 days**.
- An assessment and a plan for a fix within **30 days**.
- Credit in the release notes, if you want it.

## Scope

In scope:

- Leaks of API tokens or keys, for example in errors, logs or event objects
- Requests sent somewhere other than `api.cloudflare.com`
- Injection through configuration such as zone IDs
- Vulnerabilities in the published packages' dependencies

Out of scope:

- Vulnerabilities in Cloudflare's own services; report those to [Cloudflare](https://www.cloudflare.com/disclosure/)
- Problems caused by running the library in a browser or committing your own credentials

## Hardening tips

- Use a scoped API token with read-only permissions (**Zone → Zone → Read**, **Zone → Analytics → Read**), limited to the zones you watch.
- Restrict the token to your server's IP address and give it a TTL.
- Store the token in environment variables or a secrets manager, never in source code or client-side bundles.
- Treat event fields such as `path`, `query` and `userAgent` as untrusted input; they are controlled by whoever sent the request.
