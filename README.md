# SocialMetrics

Monthly LinkedIn engagement reporting for the **Vision RT** and **SGRT
Community** pages: likes / comments / reposts for the most recent full month,
plus a second pass that strips out Vision RT employees' interactions.

## Why the data isn't fetched automatically here

Extraction could not run inside the build environment. This is empirically
confirmed, not assumed:

| Test | Result |
|---|---|
| WebFetch → Vision RT / SGRT LinkedIn pages | 403 Forbidden |
| `curl` → same pages | 403 Forbidden |
| `curl` → LinkedIn OAuth token endpoint | **Host not in allowlist** (egress blocked) |

On top of the egress block, reading per-post engagement for an organization
page requires a **3-legged OAuth member token** held by a **page admin**, an
app approved for the **Community Management API**, and network access to
`api.linkedin.com`. A client id/secret alone (2-legged `client_credentials`)
does not grant organization social scopes.

So this repo ships the **tooling**, designed to run wherever those conditions
are met.

## Layout

```
socialmetrics/
  analyze.py          monthly aggregation + exclude-employees pass (fully tested)
  report.py           Markdown + CSV rendering
  linkedin_client.py  Community Management API pull (needs token + network)
  cli.py              `fetch` and `analyze` subcommands
data/                 sample CSVs (April 2026) used by the tests
tests/                stdlib test runner
```

## Usage

Analyze an export (works offline; this is what the tests exercise):

```bash
python -m socialmetrics.cli analyze \
    --posts data/sample_posts.csv \
    --interactions data/sample_interactions.csv \
    --employer-pattern "vision rt" --employer-pattern "visionrt.com" \
    --out-md report.md --out-csv report.csv
```

`--month` defaults to the most recent full calendar month; override with
`--month 2026-04`.

Pull from LinkedIn (run from an authenticated, network-enabled host):

```bash
python -m socialmetrics.cli fetch \
    --token "$LINKEDIN_TOKEN" \
    --channel "Vision RT=urn:li:organization:XXXX" \
    --channel "SGRT Community=urn:li:organization:YYYY" \
    --month 2026-04 --out data/posts_2026-04.csv
```

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
the API alone. To get an accurate second pass you must enrich the interactions
file with employer/title data or match against a supplied employee roster. With
an empty `actor_employer`, nobody is classified as an employee and pass 2 will
equal pass 1.

## Tests

```bash
python tests/test_analyze.py
```
