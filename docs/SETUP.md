# Local setup

The offline demo needs Python 3.12 or 3.13 and Poetry 2. It does not require an
IMDb account, session cookies, or access to the IMDb website.

```bash
poetry install
make demo
make run
```

Open [127.0.0.1:8000](http://127.0.0.1:8000). Select **Load demo dataset**, wait for
completion, then select **Create PDF report**. The dashboard offers downloads of
the dataset and report. Export settings are saved separately through the form.
The **Collect live data** action is disabled by default.

## Runtime storage

The web application and supported live collector use
`~/.local/share/imdb-portfolio` unless `IMDB_ROOT` is set. Runtime files include:

```text
<runtime root>/
├── config.yml    # Local export settings
├── uploads/      # Uploaded company sources
└── data/         # Dataset exports and reports
```

Directories and files are created when needed. The standalone demo's
`--output-dir` is independent of the web runtime root; `make demo` explicitly uses
`var/demo/` within the checkout.

To keep web runtime files in the ignored `var/` directory:

```bash
IMDB_ROOT=./var make run
```

## Environment options

| Variable | Default | Purpose |
| --- | --- | --- |
| `IMDB_ROOT` | `~/.local/share/imdb-portfolio` | Settings, upload, and output root |
| `IMDB_PORT` | `8000` | Port used by `python flask_app.py` |
| `IMDB_SECRET_KEY` | Generated per process | Optional stable Flask session signing key |
| `IMDB_ENABLE_LIVE` | Disabled | Set to `true` only for a deliberate live experiment |
| `IMDB_COOKIES_FILE` | Unset | Private JSON cookie file for the supported live collector |

Without a stable `IMDB_SECRET_KEY`, restarting the app invalidates existing
sessions. Refresh an open browser page after a restart before submitting forms.

The application reads process environment variables and does not load `.env`
automatically. For optional local overrides, copy `.env.example` to `.env`, edit
it, and export it from a POSIX shell:

```bash
cp .env.example .env
# Edit .env with your local choices before continuing.
set -a
source .env
set +a
make run
```

## Optional live collection

The live path is an experimental IMDb Pro collector. It has not been verified
against the current site, and its page selectors or authentication requirements
may need maintenance. The current company flow reads the first filmography page
only, so it is not a complete catalog export. Use it only with access and data use
permitted by the service.

To configure a deliberate experiment:

1. Provide a private JSON cookie file containing a nonempty mapping of cookie
   names to string values. Set `IMDB_COOKIES_FILE` to that file's local path.
2. Set `IMDB_ENABLE_LIVE=true` before starting the application.
3. Upload a CSV or XLSX company source with `name` and `link` columns. Each link
   must be a valid IMDb company URL. The earlier two-column, headerless input is
   also supported.
4. Choose the output format, movie status filter, and cast option; save the form.
5. Select **Collect live data**. Create a PDF after a successful dataset export.

Uploads are limited to 10 MiB. Filenames must be simple local names, without
paths. The fictional movie fixture is a report dataset, not a live company input.

The main collector can also use the saved local configuration from the CLI:

```bash
poetry run python -m imdb_extractor.movie_info_extractor
```

The same explicit live-mode and cookie-file requirements apply to that command.
A failed or empty collection reports failure rather than a completed new export.
Keep session material and runtime data in private, ignored paths; none is needed
to review or run the offline portfolio demonstration.
