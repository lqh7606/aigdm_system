# AIGDM System

中文说明请见 [README_zh.md](README_zh.md)。

AIGDM System is a Django-based clinical management system for gestational diabetes care. It supports maternal records, lab results, risk assessment, follow-up workflows, integration templates, and system configuration.

## Features

- Maternal record management
- Lab result capture and OGTT support
- Risk assessment and follow-up workflow
- Integration sources and import templates
- Role, permission, and system configuration management
- Admin UI and deployment utilities

## Tech Stack

- Python 3.9
- Django 4.2
- MySQL 8.0 for production
- mysqlclient
- xgboost, numpy, openpyxl

## Local Development

1. Create and activate the project Python environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Configure `.env` from `deploy/production.env.example`.
4. Run database migrations with `python manage.py migrate`.
5. Start the server with `python manage.py runserver`.

The project falls back to SQLite when `AIGDM_DB_ENGINE` is not set to `mysql`.

## Production Deployment

Recommended production setup:

- One Linux or Windows cloud server
- MySQL 8.0 instance
- Domain name mapped to the server
- Reverse proxy with HTTPS
- Persistent directories for `model_files`, `import_files`, `backups`, and `staticfiles`

See [Deployment Guide](DEPLOYMENT.md) for a full checklist.

## Environment Variables

Use `deploy/production.env.example` as the template. The most important values are:

- `AIGDM_SECRET_KEY`
- `AIGDM_ALLOWED_HOSTS`
- `AIGDM_DB_ENGINE`
- `AIGDM_DB_NAME`
- `AIGDM_DB_USER`
- `AIGDM_DB_PASSWORD`
- `AIGDM_DB_HOST`
- `AIGDM_DB_PORT`

## Admin Initialization

After the database is ready, run:

```bash
python manage.py initialize_system --create-admin
```

You can also add `--with-sample-data` to create one sample record and sample lab data.

## Notes

- Do not commit `.env`, `db.sqlite3`, `runtime/`, `.runtime/`, `backups/`, `import_files/`, `model_files/`, or `staticfiles/`.
- The repository includes deployment helpers such as `start-aigdm.ps1` and `scripts/one_click_mysql_deploy.ps1`.
