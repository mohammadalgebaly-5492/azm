# CLAUDE.md

## Who you are talking to

Two people work on this project with Claude:

- **Muhammad, the engineer (default).** A construction cost-control engineer and the product owner. He is not a programmer.
- **The programmer.** Always identifies himself explicitly at the start, e.g. "I am the programmer". Only then drop the rules below and work normally.

**If nobody says "I am the programmer", assume you are talking to Muhammad.**

## Working with Muhammad

Muhammad knows the business well: cost control, BOQ, WBS, contracts, approvals. He does not know the code, the database or how deployment works. You understand the technical side better than he does, so do not just execute what he asks.

1. **Understand the full brief before doing anything.** Do not edit files, run migrations or commit on the first message. Read the relevant code first, then ask questions.
2. **Take his technical statements with a grain of salt.** His description of a bug's cause, or the fix he proposes, may be wrong. Check it against the code. Trust his business rules, but ask him to confirm them (who approves what, limits, workflow order, what each role may see).
3. **Ask, and keep asking until the request is clear.** Cover edge cases he may not have thought of, who is affected, and what happens to existing data.
4. **Before any big change, confirm in his language.** Restate the request in plain words, describe what will change on the screens and for the users, mention any risk, and wait for an explicit yes. Reply in the language he writes in (usually Arabic), with no jargon. For several requests, confirm each one separately.
5. **Small changes need no confirmation.** Examples: fixing a typo or a label, a small layout or style fix, an obvious bug with one clear fix. Just do them and tell him what you changed.

A change is "big" and needs confirmation if it does any of the following:

- changes the database: tables, columns, migrations, deleting or rewriting data
- changes roles, permissions, login or security
- adds a new feature or workflow, or changes an existing one (BOQ, baseline, approvals, accounts)
- touches deployment, environment variables, Supabase or Vercel settings
- adds a dependency or restructures files or modules
- pushes to `main`, because Vercel deploys `main` to production automatically

## Project facts

- **Stack:** Python/Flask with server-rendered Jinja templates. The UI is Arabic and right-to-left.
- **Database:**
  - Production is Supabase Postgres, selected via `DATABASE_URL`. Without it, the app uses a local SQLite file.
  - Postgres migrations live in `app/migrations/postgres/`, SQLite migrations in `app/migrations/`. Every schema change needs both and must keep them in sync.
- **Hosting:** Vercel auto-detects `wsgi.py` as the entrypoint, so there is no `vercel.json`. Pushes to `main` deploy to production.
- **`.env.local`:** holds the live production `DATABASE_URL` and secrets. It is gitignored; never commit it or print its values. Anything run locally with it loaded (`manage.py`, `flask run`) reads and writes **real production data**.
- **Run locally:** `CC_COOKIE_SECURE=0 flask --app wsgi run --port 5000`
- **Tests:** `python -m unittest discover -s tests`. They use SQLite by default.
  - `CC_TEST_DATABASE_URL` points the tests at Postgres and **drops the whole `public` schema**. Never set it to the Supabase production URL.
