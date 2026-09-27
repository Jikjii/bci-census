# BCI Census

How many people are living with an implanted brain-computer interface? Published answers range from about 50 to about 250. The BCI Census publishes a verified floor, program by program, with a source for every number, and updates it every week.

Site: https://jikjii.github.io/bci-census/

Between editions, [the Wire](#the-wire-breaking-bci-news-on-your-phone) watches the same primary sources minute by minute and sends each new item to your phone with a draft post.

## How it works

Every Monday a GitHub Action:

1. pulls BCI trials from ClinicalTrials.gov, device decisions from openFDA and Form D filings from SEC EDGAR,
2. classifies each trial (implanted BCI or not, chronic or acute) and links it to a program,
3. merges that with the sourced facts in `data/curated/`,
4. computes the verified floor, writes a snapshot and a list of what changed since last week,
5. rebuilds the site in `docs/` and drafts the week's X thread in `posts/`, then opens an issue with the draft.

The rules are in [METHODOLOGY.md](METHODOLOGY.md).

## Run it locally

Python 3.10 or newer (on a Mac, type `python3` wherever this says `python`).

```bash
pip install -r requirements.txt
export SEC_USER_AGENT="BCI Census your-email@example.com"   # SEC requires a contact email
python -m census build             # live pull from all sources
python -m census build --offline   # curated facts only, no network
python -m pytest -q
```

Outputs:

| Path | What it holds |
|---|---|
| `data/latest/` | `census.json`, `trials.json`, `fda.json`, `form_d.json`, `changes.json`, plus CSVs |
| `data/snapshots/YYYY-MM-DD/` | The same files, frozen each week so changes can be diffed |
| `docs/` | The static site served by GitHub Pages |
| `posts/YYYY-MM-DD.md` | The draft X thread for that week |

## One-time setup on GitHub

1. Create a public repo named `bci-census` and push this folder to `main`.
2. **Settings → Secrets and variables → Actions → New repository secret:** `SEC_USER_AGENT` = `BCI Census <your email>`. Optional: `OPENFDA_API_KEY` (free at open.fda.gov) for higher rate limits.
3. **Settings → Pages:** Source = Deploy from a branch, Branch = `main`, folder = `/docs`.
4. **Settings → Actions → General → Workflow permissions:** Read and write.
5. **Actions → weekly-census → Run workflow** once. This first live run is the first edition: it pulls every source, publishes the real numbers to the site, and opens an issue titled "X draft for DATE" that holds the launch thread.

## Every week

The Action runs Mondays at 12:17 UTC. Then:

1. Open the new "X draft" issue and skim the site's "What changed this week" section.
2. If a trial was misclassified or a count looks wrong, fix it (below) and re-run the workflow; the draft updates.
3. Post the thread from @SiegeGrell: paste post 1, then add each next post to the thread. Every post is already checked against X's 280-character limit (links count as 23).
4. Close the issue.

## Fixing the data

- Wrong trial call: add the NCT ID to `data/curated/trial_overrides.yaml` with a reason (`in_scope`, `duration` or `program`).
- A paper or sponsor gives the number actually implanted in a trial: add `implanted` and `source_url` to that trial's override; it replaces the enrollment count.
- New count, approval or round: add it to the matching file in `data/curated/` with a source URL, date and tier.
- Something you can't source yet: add it to `data/curated/verify_queue.yaml`.

Corrections from anyone are welcome as issues. Include a source link.

## The Wire: breaking BCI news on your phone

The census is weekly. The Wire runs every minute: it checks the places where BCI news breaks first and sends each new item to your phone with a draft post. The draft is under 280 characters and has no link, because X shows posts with links to fewer people; the link goes in your first reply. Each alert also says what the census already knows about the company, and the draft includes it when it fits.

| Source | Checked every | What reaches you |
|---|---|---|
| SEC filings by tracked companies | 1 min | Every filing; a Form D (money raised) is marked URGENT |
| News, English (Google News) | 3 min | Company press releases (URGENT for tracked companies) and major outlets; other coverage waits for the digest |
| SEC full-text search | 5 min | Any company's new filing that mentions brain-computer interfaces |
| News, Chinese (Google News) | 5 min | Approvals, financings and first cases in China; other coverage waits for the digest |
| Journals: Nature, Science, NEJM and field journals | 10 min | New papers as embargoes lift |
| FDA press releases | 15 min | Releases that mention BCIs or a tracked company (URGENT) |
| ClinicalTrials.gov | 1 h | New implanted-BCI trials (URGENT for tracked programs); status and enrollment changes |
| Federal Register | 2 h | Rules and notices that mention BCIs (URGENT) |
| PubMed | 2 h | Papers, in the digest |
| bioRxiv and medRxiv | 4 h | Preprints, in the digest |
| Company job boards | 6 h | Hiring in a new city or country; clinical and regulatory roles |
| openFDA | 12 h | 510(k) and PMA decisions for tracked companies |

From 23:00 to 07:00 your time, alerts wait for the 07:00 digest; set `quiet_urgent` to let URGENT ones ring at night. Digests at 07:00 and 19:00 also collect the lower-priority items and come with an "Overnight in BCI" or "Today in BCI" draft. The first run records everything that already exists without alerting and sends a "BCI Wire is watching..." message; after that you only hear about new items. If a source fails five times in a row, you get a "Wire health" alert.

### 1. Make your alert bot (Telegram, free, about 5 minutes)

1. Install Telegram on your phone. Open **@BotFather**, send `/newbot`, and choose a name and a username ending in `bot`. BotFather replies with a token.
2. Open your new bot and press **Start**.
3. On your computer, in this folder (the Wire needs only Python 3.10 or newer; nothing to install):

```bash
export TELEGRAM_BOT_TOKEN="the token from BotFather"
python -m wire telegram-setup        # prints TELEGRAM_CHAT_ID=...
export TELEGRAM_CHAT_ID="the number it printed"
python -m wire test                  # your phone should buzz
```

Every alert has a **Draft post** button that opens X with the text filled in, and the draft also sits in a block that copies when you tap it.

Why Telegram and not ntfy on AWS: ntfy.sh's free tier counts messages per IP address, and AWS Lambda shares its addresses with other customers, whose traffic can use up your daily quota ([reported for Cloudflare Workers in September 2026](https://github.com/binwiederhier/ntfy/issues/1963)). Telegram limits each bot instead. ntfy still works when the Wire runs on your own computer (`NTFY_TOPIC=your-topic`), and both channels can run at once.

### 2. Try it on your computer

Set `SEC_USER_AGENT` as in "Run it locally" (without it the two SEC sources stay off), then:

```bash
python -m wire sources                  # what it watches and how often
python -m wire run --dry-run --force    # first pass: records what exists, prints the startup notice
python -m wire run --dry-run --force    # later passes print anything new
python -m wire loop                     # keep running every minute until Ctrl+C
```

### 3. Run it on AWS (about $1 a month)

You need an AWS account, the AWS CLI v2 and Terraform 1.5 or newer (on a Mac: `brew install awscli hashicorp/tap/terraform`; OpenTofu works too, with `tofu` in place of `terraform`).

```bash
aws login                                                  # or: aws configure
eval "$(aws configure export-credentials --format env)"    # hands those credentials to Terraform
cd infra/wire
cp terraform.tfvars.example terraform.tfvars               # fill in: SEC contact, bot token, chat id, time zone, budget email
terraform init
terraform apply                                            # review the plan, type yes
eval "$(terraform output -raw send_test_alert)"            # one test alert from AWS
```

This creates one Lambda function (Python, arm64, 256 MB) that EventBridge wakes every minute, a DynamoDB table for what it has already seen, a log group kept for 14 days, and an AWS Budgets alert that emails you at 50% and 100% of $10 a month for the whole account. A failed run is not retried; the next minute picks up where it left off.

Cost: about 43,200 runs a month, inside Lambda's always-free allowance of 1 million requests and 400,000 GB-seconds a month. DynamoDB and logs add well under $1.

Day to day:

- Change a setting: edit `terraform.tfvars`, then `terraform apply`. Pause with `paused = true`; remove everything with `terraform destroy`.
- Check on it: `eval "$(terraform output -raw check_sources)"` shows when each source last ran and any error; `eval "$(terraform output -raw follow_logs)"` streams each run.
- New code: pull, then `terraform apply` uploads it.
- Census updates reach the alerts by themselves: the Wire reads the site's `census.json` every hour.
- Secrets: the bot token and SEC contact live in the function's environment (encrypted by AWS) and in your local `terraform.tfstate`. Git ignores `terraform.tfvars` and the state; keep both off shared drives.

### Settings

On AWS these are Terraform variables (see `infra/wire/variables.tf`); locally they are environment variables.

| Environment variable | Default | Meaning |
|---|---|---|
| `SEC_USER_AGENT` | none | `BCI Census you@example.com`; SEC asks automated tools for a contact |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | none | Telegram alerts |
| `NTFY_TOPIC`, `NTFY_SERVER`, `NTFY_TOKEN` | none, `https://ntfy.sh`, none | ntfy alerts |
| `WIRE_TZ` | `America/New_York` | Your time zone |
| `WIRE_QUIET_HOURS` | `23-7` | Local hours when only digests go out, or `off` |
| `WIRE_QUIET_URGENT` | `false` | `true` lets URGENT alerts ring at night |
| `WIRE_DIGEST_HOURS` | `7,19` | Local digest hours |
| `WIRE_JOB_BOARDS` | none | Extra job boards as JSON (below) |
| `WIRE_DISABLED_SOURCES` | none | Comma-separated source names |
| `WIRE_NEWS_QUERY`, `WIRE_NEWS_QUERY_ZH` | built in | Google News searches |
| `OPENFDA_API_KEY` | none | Optional, for higher openFDA limits |

Job boards: the Wire starts with Neuralink's Greenhouse board. To add a company, find its careers page; the provider and slug are in the URL (`boards.greenhouse.io/<slug>`, `jobs.lever.co/<slug>` or `jobs.ashbyhq.com/<slug>`). In `terraform.tfvars`:

```hcl
job_boards = [{ program = "<id from data/curated/programs.yaml>", provider = "lever", slug = "<slug>" }]
```

Locally: `export WIRE_JOB_BOARDS='[{"program": "<id>", "provider": "lever", "slug": "<slug>"}]'`. A new board is recorded quietly on its first check, like everything else.

## Layout

```
census/            Python package: sources, classifier, census math, diff, post and site builders
wire/              The Wire: source watchers, drafts, alerts, digests (standard library only)
infra/wire/        Terraform that runs the Wire on AWS
data/curated/      Hand-verified facts (programs, counts, approvals, rounds, overrides, verify queue)
data/latest/       Generated each run
data/snapshots/    Generated each run, one folder per date
docs/              Generated site (GitHub Pages)
posts/             Generated X drafts; the first edition's draft is the launch thread
tests/             Pytest suite with API-shaped fixtures
```

## Licenses and disclaimers

Code: MIT. Data in `data/` and `docs/data/`: CC BY 4.0, credit "BCI Census".

Trial data comes from ClinicalTrials.gov, device data from openFDA and filings from SEC EDGAR, all public U.S. government sources; none of them endorse this project. This is not medical advice. No personal data is collected or published.
