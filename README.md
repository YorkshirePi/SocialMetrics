# SocialMetrics

Monthly LinkedIn engagement reporting for the **Vision RT** and **SGRT
Community** pages: likes / comments / reposts for the most recent full month,
plus a second pass that strips out Vision RT employees' interactions.

One single-file executable: **`socialmetrics.py`**.

| Subcommand | Role | Network |
|---|---|---|
| `auth` | Run the OAuth 2.0 Authorization Code flow and print an access token | Needs LinkedIn access |
| `fetch` | Pull posts + engagement from LinkedIn into a posts CSV (runs `auth` automatically if no token) | Needs LinkedIn access |
| `analyze` | Aggregate the CSV(s) into the monthly report | Offline |

## Authentication (built-in 3-legged OAuth)

You do **not** need to pre-mint a token. `auth`/`fetch` implement the full
Authorization Code flow with your app's **client id + client secret**:

1. the tool prints (and opens) the LinkedIn authorization URL;
2. you approve in your already-logged-in browser;
3. LinkedIn redirects to a local callback the tool is listening on;
4. the tool exchanges the code + client id + secret for an access token.

Prerequisites on the LinkedIn app (Developer Portal), not extra secrets:

* the **redirect URI** you pass (default `http://localhost:8765/callback`)
  must be listed under the app's *Authorized redirect URLs*;
* the app must be **approved for the scopes** requested (default
  `r_organization_social rw_organization_admin`, i.e. the Community
  Management API), and the authorizing user must **admin the page**.

Run from a host with network egress to `www.linkedin.com` /
`api.linkedin.com`. The build sandbox blocks this (confirmed by test:
`Host not in allowlist`), so the OAuth and fetch steps run on your machine.

```bash
# one-off: get a token
./socialmetrics.py auth --client-id <ID>          # prompts for secret (hidden)
# → prints:  export LINKEDIN_TOKEN='...'

# or just fetch — it runs the OAuth flow inline when no token is present
./socialmetrics.py fetch --client-id <ID> \
    --vision-rt-urn urn:li:organization:<VisionRT-ID> \
    --month 2026-04 --out data/vrt_2026-04.csv
```

Credentials may also come from `--client-secret`, `$LINKEDIN_CLIENT_ID`,
`$LINKEDIN_CLIENT_SECRET`, `--token`, or `$LINKEDIN_TOKEN`. Use
`--no-browser` for headless auth (URL is printed), `--no-login` to require a
pre-minted token instead of the flow.

## Usage

Pull Vision RT only (OAuth runs inline), then analyze offline:

```bash
./socialmetrics.py fetch --client-id <ID> \
    --vision-rt-urn urn:li:organization:<VisionRT-ID> \
    --month 2026-04 --out data/vrt_2026-04.csv

./socialmetrics.py analyze --posts data/vrt_2026-04.csv \
    --interactions data/vrt_interactions_2026-04.csv \
    --employer-pattern "vision rt" --employer-pattern "visionrt.com" \
    --out-md report.md --out-csv report.csv
```

Add `--channel "SGRT Community=urn:li:organization:<ID>"` (repeatable) to
include more channels. `--month` defaults to the most recent full calendar
month. Omit `--interactions` to report from post-level totals only (no
employee-stripped pass).

## Input formats

**posts** — `channel,post_id,posted_at,likes,comments,reposts`
**interactions** (optional, enables the employee-stripped pass) —
`channel,post_id,interaction_type,actor_name,actor_employer`

`interaction_type` accepts like/comment/repost (and reaction/share aliases).

## The employee-stripping limitation (read this)

The second pass infers Vision RT employment from the `actor_employer` text on
each interaction row (case-insensitive substring match against
`--employer-pattern`). LinkedIn's like/comment endpoints return actor member
URNs but **never the actor's employer**, so this column cannot be populated by
the API alone. For an accurate second pass, enrich the interactions file with
employer/title data or match against a supplied employee roster. With an empty
`actor_employer`, nobody is classified as an employee and pass 2 equals pass 1.

## Tests

```bash
python tests/test_analyze.py
```
