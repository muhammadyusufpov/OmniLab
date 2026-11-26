# One-command deployment

OmniLab can run on any standard Linux host with Python 3 and an HTTPS reverse
proxy. The deployment command keeps its virtual environment, SQLite database,
and collected static files in one configurable directory.

## Start or update the service

Set the production environment in the host's protected settings, then run this
from a clean checkout:

```bash
./deploy/omnilab.sh
```

The command is safe to repeat. It installs the declared Python requirements,
applies migrations, collects static files for WhiteNoise, and replaces itself
with Gunicorn. Run it under the host's service manager so restarts use the same
command and environment.

## Environment

`OMNILAB_DJANGO_SECRET_KEY` is the only variable required to start. Generate a
long random value once, store it in the host's protected environment, and keep
the same value across restarts. The command exits before changing the database
when this variable is missing.

Set `OMNILAB_ALLOWED_HOSTS` to the public host names accepted by Django,
separated by commas. It defaults to the current Render host plus localhost, so a
different public host must set its own name. Do not include schemes or paths.

Set `OMNILAB_PUBLIC_ORIGIN` when the public address changes. This one HTTPS
origin controls canonical tags, social preview URLs, prepared-demo links,
`sitemap.xml`, and the sitemap address in `robots.txt`. Do not include a path,
query, fragment, credentials, or trailing slash. Keep `OMNILAB_NOINDEX=true` on
temporary deployments independently of this origin setting.

The remaining deployment variables are optional:

| Name | Default | Purpose |
|---|---|---|
| `OMNILAB_DEPLOY_DIR` | `.deploy` | Parent for the virtual environment and persistent runtime files. |
| `OMNILAB_DATABASE_PATH` | `.deploy/data/db.sqlite3` | SQLite database path. Mount or back up its parent directory. |
| `OMNILAB_REACTION_RATE_LIMIT_DATABASE_PATH` | Beside `OMNILAB_DATABASE_PATH` | Shared SQLite counter for reaction limits across Gunicorn workers. |
| `OMNILAB_STATIC_ROOT` | `.deploy/staticfiles` | WhiteNoise collection target. |
| `OMNILAB_PUBLIC_ORIGIN` | `https://omnilab-bk8q.onrender.com` | HTTPS origin for every absolute public discovery URL. |
| `OMNILAB_NOINDEX` | unset | Set to `true` on temporary or preview deployments to send `X-Robots-Tag: noindex, nofollow` on every response. |
| `OMNILAB_PYTHON` | `python3` | Python executable used to create the virtual environment. |
| `PORT` | `8000` | Port Gunicorn listens on. |
| `WEB_CONCURRENCY` | `2` | Gunicorn worker count. Reaction limits are shared across workers. |
| `GUNICORN_TIMEOUT` | `30` | Worker timeout in seconds. |

The Contact form also needs the `OMNILAB_EMAIL_*` and `OMNILAB_CONTACT_*`
variables listed in `.env.example`. The lab and guide pages still start without
SMTP, but Contact delivery will fail until those values are valid.

## Proxy and health check

Terminate HTTPS at the host's reverse proxy, forward requests to `PORT`, and
preserve the original host. Send `X-Forwarded-Proto: https`; OmniLab trusts that
header in production and redirects plain HTTP requests to HTTPS.

Use `GET /health/` as the liveness check. It returns HTTP 200 with `ok` and does
not touch the database, SMTP, or analytics. A check that reaches Gunicorn
directly must send the public `Host` value and `X-Forwarded-Proto: https`.

After the service restarts, check the homepage, chemistry lab, and a current
reaction guide with one read-only command:

```bash
python3 deploy/check_routes.py https://omnilab-bk8q.onrender.com
```

The command prints PASS or FAIL for each route and exits non-zero if any route
does not return HTTP 200. Run it again after later releases. It does not submit
a reaction or change student data. The liveness check and full journey check
remain separate steps.

## Failure behavior

The command stops with a non-zero status when the secret is missing, a numeric
process setting is invalid, Python is unavailable, dependencies cannot install,
a migration fails, or static collection fails. Gunicorn starts only after every
preflight step succeeds. Keep the SQLite directory on persistent storage before
moving traffic, and stop the old process before starting a second copy against
the same SQLite file.
