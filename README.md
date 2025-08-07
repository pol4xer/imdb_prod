# imdb-public

**IMDB Info Extractor**  
_A public showcase repository demonstrating Python, ETL, web-scraping, PDF generation, and Flask skills._

---

## 🚀 Project Overview

`imdb-public` is a lightweight Python application for extracting, processing, and exporting movie data from IMDb.
Originally part of a private codebase, this sanitized demo shows off:

- **Web scraping & ETL** with Scrapy-style extractors
- **Data transformation** using Pandas & Jinja2 templates
- **PDF report generation** via XHTML2PDF
- **RESTful web interface** powered by Flask & Flask-SocketIO
- **Configurable workflows** using YAML
- **Deployment automation** (Makefile, Procfile)

This repo is intended for recruiters and hiring managers to evaluate coding style, project structure, and end-to-end
delivery.

---

## 🔧 Features

- **`movie_extractor.py` & friends**: Modular extractor classes for movies, producers, and related entities
- **Data pipelines**: Read → transform → export (CSV, Excel, PDF)
- **PDF report**: Dynamic movie report generation with Jinja2 templates
- **Web UI**: Simple Flask app (`flask_app.py`) with upload, config form, and live progress updates
- **Configuration**: `config.yml` to tweak scraping targets, output formats, and processing options
- **Uploads & Templates**: Customizable HTML/PDF templates in `templates/`
- **Automation**:
    - `Makefile` for linting and test tasks
    - `install.sh` for setting up environment
    - `Procfile` for Heroku-style deployment

---

## 🛠️ Tech Stack

- **Language**: Python 3.9+
- **Web scraping**: Custom scripts (requests / BeautifulSoup style)
- **Data processing**: Pandas, Jinja2
- **PDF generation**: XHTML2PDF
- **Web framework**: Flask, Flask-SocketIO
- **Config & templating**: PyYAML, Jinja2
- **Linting & formatting**: Ruff
- **Deployment**: Docker (optional), Heroku / Procfile  
