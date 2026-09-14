# Development

The project uses Python 3.12 or 3.13, Poetry 2, a committed lockfile, Ruff, and
pytest. It runs from a source checkout; Poetry is configured without package
installation mode.

```bash
poetry install
make check
make demo
```

## Commands

| Command | Purpose |
| --- | --- |
| `make install` | Install the Poetry environment |
| `make run` | Start the local Flask dashboard on port 8000 by default |
| `make demo` | Create a fictional CSV export and PDF under `var/demo/` |
| `make lint` | Check Ruff lint rules and formatting |
| `make test` | Run offline tests |
| `make check` | Validate metadata/lockfile, run linting, and execute tests |
| `make format` | Apply Ruff fixes and formatting |
| `poetry check --lock` | Validate dependency metadata and the lockfile |

To choose a separate demo destination:

```bash
poetry run python -m imdb_extractor.demo --output-dir var/another-demo
```

The command writes `demo_movies.csv` and `demo_report.pdf`. It uses the source
fixture [`examples/movies.csv`](../examples/movies.csv), whose three films and
associated people and companies are invented for this project.

## Tests

Tests use temporary runtime directories and fixture data. The report tests
exercise real PDF generation; extractor tests use local response fixtures and
check request construction and data handling without making IMDb requests.
Web tests configure the Flask application factory for isolated execution.

Focus areas include:

- CSV/XLSX inputs, explicit output columns, and earlier input-format compatibility;
- validated company links, instance-local spider state, and live-mode gating;
- list-field parsing, HTML escaping, PDF resource restrictions, and error handling;
- configuration paths, form validation, local task status, and artifact downloads.

A passing suite establishes the tested local behavior. It does not establish
live access to IMDb, complete extraction results, or production deployment
readiness.

## Changing the prototype

Keep shared file-format rules in `tabular.py` and runtime configuration in
`settings.py`. Add focused tests when changing input validation, extraction
parsing, or report handling. Use fictional records in fixtures and keep local
cookies, uploads, exports, and environment files out of version control.

The dashboard is deliberately a local tool. Additional workers, authentication,
or deployment infrastructure require a separate design rather than assuming the
current in-memory task state can serve multiple users.
