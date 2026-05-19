# SocialMetrics

Monthly LinkedIn engagement reporting for the **Vision RT** and **SGRT
Community** pages: likes / comments / reposts for the most recent full month,
plus a second pass that strips out Vision RT employees' interactions.

Two single-file deliverables, split by what each half can actually do:

| File | Role | Network |
|---|---|---|
| `socialmetrics.py` | **Acquisition + analysis.** `fetch` pulls posts+engagement from LinkedIn; `analyze` builds the report. | `fetch` needs LinkedIn access; `analyze` is offline |
| `socialmetrics.html` | **Analysis only**, fully in-browser. Drop in a CSV, get the report. | None — never touches the network |

## Why acquisition is a `.py`, not the browser

A plain HTML page **cannot** read LinkedIn using your logged-in session: the
browser's Same-Origin Policy blocks any non-`linkedin.com` page from making
authenticated requests to LinkedIn and reading the response with your cookies.
That is a deliberate security boundary, not a configuration gap. So all
acquisition lives in `socialmetrics.py fetch`, which uses the official
LinkedIn Community Management API with a proper token.

`socialmetrics.html` exists purely so the **analysis** can run anywhere with
zero setup — load the CSV that `fetch` (or a LinkedIn page-admin export)
produced. Its engine is a verified line-for-line port of the Python one
(identical outputs on the sample data).

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
month.

Browser analysis: open `socialmetrics.html`, pick the posts CSV (and optional
interactions CSV), click **Analyze**, download the report.

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
