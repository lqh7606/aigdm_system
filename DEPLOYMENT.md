# Deployment Guide

This project is designed to run behind a reverse proxy with MySQL 8.0.

## What You Need

- A cloud server or virtual machine
- A domain name pointing to the server
- MySQL 8.0, either on the same host or as a managed cloud database
- Python 3.9 and the project dependencies
- HTTPS certificate
- Persistent storage for uploads, model files, backups, and static files

## Recommended Architecture

- Browser -> HTTPS reverse proxy -> Django app
- Django app -> MySQL 8.0
- Django app -> local directories for files and static assets

## Preparation Checklist

1. Point the domain to the server.
2. Open ports 80 and 443 in the cloud security group and firewall.
3. Create a MySQL database and user for the application.
4. Copy `deploy/production.env.example` to `.env` and fill in production values.
5. Set `AIGDM_ALLOWED_HOSTS` to the domain and server IP.
6. Set `AIGDM_SECRET_KEY` to a long random value.
7. Set `AIGDM_DB_HOST`, `AIGDM_DB_NAME`, `AIGDM_DB_USER`, and `AIGDM_DB_PASSWORD`.
8. Ensure the directories in `.env` exist and are writable.

## Database Setup

Create the database and user in MySQL 8.0, then grant privileges on the application database.

If MySQL runs on the same server, `127.0.0.1` is usually enough.
If it is a managed service, use the service endpoint and allow the server IP.

## Application Setup

1. Install Python dependencies.
2. Run `python manage.py migrate`.
3. Run `python manage.py initialize_system --create-admin`.
4. Optionally run `python manage.py initialize_system --create-admin --with-sample-data` in a non-production sandbox.
5. Run `python manage.py collectstatic --noinput` if you are serving static assets from `STATIC_ROOT`.

## Reverse Proxy

Use Nginx, IIS, or another reverse proxy to expose the app on your domain.
Make sure the proxy passes `X-Forwarded-Proto` so Django knows requests are HTTPS.

## Launch

Start Django using a production-safe process manager or service wrapper.
Avoid exposing the development server directly to the internet.

## Verification

After deployment, verify:

- The domain opens over HTTPS
- Login works
- The admin account exists
- The database connection is healthy
- Static files load correctly
- Upload and import paths are writable

## Troubleshooting

- If Django rejects the host, check `AIGDM_ALLOWED_HOSTS`.
- If login or session cookies misbehave on HTTPS, confirm the reverse proxy is setting `X-Forwarded-Proto`.
- If database access fails, verify MySQL host, port, username, password, and grants.
- If large file uploads fail, check disk quotas and permissions on the file directories.
