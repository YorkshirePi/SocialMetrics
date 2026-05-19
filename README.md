# SocialMetrics

Monthly LinkedIn engagement reporting for the **Vision RT** and **SGRT
Community** pages: likes / comments / reposts for the most recent full month,
plus a second pass that strips out Vision RT employees' interactions.

One single-file executable: **`socialmetrics.py`**.

| Subcommand | Role | Network |
|---|---|---|
| `fetch` | Pull posts + engagement from LinkedIn into a posts CSV | Needs LinkedIn access |
| `analyze` | Aggregate the CSV(s) into the monthly report | Offline |

## LinkedIn access requirements for `fetch`

In the build sandbox these can't be met (egress to `api.linkedin.com` is
blocked; confirmed by test). Run `fetch` from a host that has:

* network egress to `api.linkedin.com`;
* a **3-legged OAuth member access token** held by an **admin of the target
  page(s)**, scopes `r_organization_social` (+ `rw_organization_admin`);
* the app **approved for the Community Management API**.

A client id/secret alone (2-legged `client_credentials`) does **not** grant
organization-social scopes.

## Usage

Pull Vision RT only, then analyze (run `fetch` where LinkedIn is reachable):

```bash
./socialmetrics.py fetch --token "$LINKEDIN_TOKEN" \
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
