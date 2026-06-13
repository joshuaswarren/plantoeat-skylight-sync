# plantoeat-skylight-sync

One-way sync of a [Plan to Eat](https://www.plantoeat.com/) meal plan into a
[Skylight Calendar](https://www.skylightframe.com/)'s **Meals** (recipes + planned
meals), built on [`pyskylight`](https://github.com/joshuaswarren/pyskylight).

Plan to Eat is the source of truth; every run is an idempotent reconcile. Re-running
with no meal-plan changes performs zero writes.

## How it works

```
Plan to Eat iCal feed  ──fetch──►  parse VEVENTs  ──►  reconcile  ──►  Skylight Meals
 /planner/{ID}/…/plantoeat-ical                          (diff)         - upsert Recipe
                                                                        - upsert Sitting
```

1. Fetch the Plan to Eat iCal feed (the supported export; no Plan to Eat API exists).
2. Parse each event into `{date, slot, title, description}` (slot inferred from a
   course keyword, the event time, or a configurable default).
3. For each planned meal in the window: ensure the **recipe** exists (reuse by title),
   then ensure a **sitting** (date + meal category + recipe) exists.
4. A local state file maps each meal to its Skylight ids, so runs are idempotent and
   opt-in deletion only ever touches sittings this tool created.

> **Lossy by nature:** the iCal feed gives meal names and (depending on the chosen
> variant) ingredients/notes as text — not structured recipes. Meal-slot inference is
> best-effort; all-day events fall back to `SYNC_DEFAULT_SLOT`.
>
> **Skylight Plus:** the Meals feature requires an active Skylight Plus subscription.

## Configuration

Set via environment (or a `.env` file — see [`.env.example`](.env.example)). Secrets
may be `op://` 1Password references.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `PTE_ICAL_URL` | yes | — | Plan to Eat iCal feed URL (a secret) |
| `SKYLIGHT_EMAIL` / `SKYLIGHT_PASSWORD` | yes | — | Skylight login |
| `SKYLIGHT_FRAME_ID` | yes | — | Skylight household id (`skylight frames`) |
| `SYNC_PAST_DAYS` | no | 1 | days of history to reconcile |
| `SYNC_FUTURE_DAYS` | no | 21 | days ahead to reconcile |
| `SYNC_DEFAULT_SLOT` | no | dinner | slot for events with no inferable course |
| `SYNC_ALLOW_DELETE` | no | false | remove sittings this tool made that left the feed |
| `SYNC_STATE_PATH` | no | XDG state dir | local reconcile state file |

Find your Plan to Eat feed URL in the app: **Share Meal Plan** → pick a variant
(*All* or *Recipes*) → copy the iCal URL.

## Usage

```bash
pip install -e .            # plus: pip install pyskylight  (or from git)

pte-skylight-sync plan      # dry run: print what would change, write nothing
pte-skylight-sync run       # apply
pte-skylight-sync run --allow-delete
```

Every command prints a JSON report.

### Container (recommended for scheduled syncing)

```bash
cp .env.example .env        # fill in (op:// refs OK)
docker compose up -d --build
```

The container runs the sync every `SYNC_INTERVAL` seconds (default 3h) and keeps its
state on the `./data` volume. Or run `pte-skylight-sync run` from cron instead.

## Development

```bash
pip install -e ../pyskylight        # sibling client (until it's on PyPI)
pip install -e ".[dev]"
pytest                              # full suite + coverage (fails under 90%)
pre-commit run --all-files
```

## Legal

Unofficial; not affiliated with Plan to Eat or Skylight. Personal use, your own
accounts only. The Plan to Eat feed URL and Skylight token are secrets — never commit
them. [MIT License](LICENSE).
