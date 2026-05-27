# Production Deployment Guide

This document outlines the steps to prepare and deploy the Sabaiko CSIT platform to production.

## Pre-Deployment Checklist

### 1. Environment Configuration
- [ ] Copy `.env.example` to `.env` (for production server only)
- [ ] Update `DJANGO_SECRET_KEY` with a secure random value
  ```bash
  python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```
- [ ] Set `DJANGO_DEBUG=False`
- [ ] Update `DJANGO_ALLOWED_HOSTS` with your domain(s)
- [ ] Update `FRONTEND_URL` and `FRONTEND_BASE_URL` with production URLs

### 2. Security Settings
- [ ] Set `DJANGO_SECURE_SSL_REDIRECT=True` (requires HTTPS)
- [ ] Set `DJANGO_SESSION_COOKIE_SECURE=True`
- [ ] Set `DJANGO_CSRF_COOKIE_SECURE=True`
- [ ] Set `DJANGO_SECURE_HSTS_SECONDS=31536000` (1 year)
- [ ] Set `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True`
- [ ] Set `DJANGO_SECURE_HSTS_PRELOAD=True`

### 3. CORS & CSRF Configuration
- [ ] Update `DJANGO_CSRF_TRUSTED_ORIGINS` with production domain
- [ ] Update `DJANGO_CORS_ALLOWED_ORIGINS` with production frontend URL
- [ ] Ensure protocols are `https://` not `http://`

### 4. Google OAuth Credentials
- [ ] Verify `GOOGLE_CLIENT_ID` is set (currently: `594875084700-7r78gapr8o9po7dj8vhq0m94ghb4klqh.apps.googleusercontent.com`)
- [ ] Verify `GOOGLE_CLIENT_SECRET` is set (check `.env` - never commit secrets)
- [ ] Ensure Google OAuth redirect URI matches your deployment URL: `https://api.ramrocsit.com/api/auth/google/callback/`

### 5. Email Configuration
- [ ] Update `DJANGO_EMAIL_BACKEND` from console to SMTP
- [ ] Configure `DJANGO_EMAIL_HOST`
- [ ] Configure `DJANGO_EMAIL_PORT`
- [ ] Set `DJANGO_EMAIL_HOST_USER`
- [ ] Set `DJANGO_EMAIL_HOST_PASSWORD`
- [ ] Set `DJANGO_EMAIL_USE_TLS=True`
- [ ] Update `DJANGO_DEFAULT_FROM_EMAIL`

### 6. Database Configuration
- [ ] Use a production database (PostgreSQL recommended, not SQLite)
- [ ] Set `DATABASE_URL` environment variable if using django-environ
- [ ] Run migrations: `python manage.py migrate`
- [ ] Create superuser: `python manage.py createsuperuser`

### 7. Static Files
- [ ] Configure static files storage (AWS S3, local, etc.)
- [ ] Run `python manage.py collectstatic --no-input`
- [ ] Configure web server to serve static files

### 8. File Security
- [ ] Ensure `.env` file is NOT committed to version control
- [ ] Verify `.gitignore` includes `.env` and `.env.*` (except `.env.example`)
- [ ] Never commit `db.sqlite3` (unless absolutely necessary for testing)
- [ ] Ensure proper file permissions on production server
  ```bash
  chmod 600 .env  # Only owner can read
  chmod 755 csit_platform/
  ```

### 9. HTTPS & SSL
- [ ] Obtain SSL certificate (Let's Encrypt recommended)
- [ ] Configure web server (Nginx/Apache) with SSL
- [ ] Set up auto-renewal for certificates
- [ ] Ensure `SECURE_SSL_REDIRECT=True` redirects HTTP to HTTPS

### 10. Web Server Setup
- [ ] Install and configure Gunicorn or similar WSGI server
- [ ] Configure Nginx or Apache as reverse proxy
- [ ] Set up process manager (systemd, supervisor, etc.)
- [ ] Configure log rotation

### 11. Frontend Configuration
- [ ] Copy `noteshare/.env.example` to `noteshare/.env.local` or `.env.production.local`
- [ ] Update `NEXT_PUBLIC_API_URL` to production backend URL
- [ ] Verify `NEXT_PUBLIC_GOOGLE_CLIENT_ID` matches backend configuration
- [ ] Build optimized frontend: `npm run build`

### 12. Monitoring & Logging
- [ ] Set up application logging
- [ ] Configure error tracking (Sentry, etc.)
- [ ] Set up uptime monitoring
- [ ] Configure backup strategy

## Deployment Steps

1. **Prepare Production Server**
   ```bash
   # SSH into production server
   cd /path/to/deployment
   git clone <repository>
   cd csit-main
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with production values
   nano .env
   ```

4. **Initialize Database**
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

5. **Collect Static Files**
   ```bash
   python manage.py collectstatic --no-input
   ```

6. **Start Application**
   ```bash
   # Using Gunicorn
   gunicorn csit_platform.wsgi:application --bind 0.0.0.0:8000 --workers 4
   ```

## Environment Variables Reference

### Required for Production
- `DJANGO_DEBUG=False`
- `DJANGO_SECRET_KEY=<secure-random-key>`
- `DJANGO_ALLOWED_HOSTS=<your-domains>`
- `GOOGLE_CLIENT_ID=594875084700-7r78gapr8o9po7dj8vhq0m94ghb4klqh.apps.googleusercontent.com`
- `GOOGLE_CLIENT_SECRET=<your-secret>`
- `FRONTEND_URL=https://ramrocsit.com`

### Recommended for Production
- `DJANGO_SECURE_SSL_REDIRECT=True`
- `DJANGO_SESSION_COOKIE_SECURE=True`
- `DJANGO_CSRF_COOKIE_SECURE=True`
- `DJANGO_SECURE_HSTS_SECONDS=31536000`
- `DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`

## Security Considerations

### Secrets Management
- Use environment variables for all secrets
- Never commit `.env` file
- Use secrets management tools (AWS Secrets Manager, HashiCorp Vault, etc.)
- Rotate secrets regularly

### Access Control
- Use strong database passwords
- Restrict SSH access (key-based auth only)
- Use firewall rules to limit access
- Implement API rate limiting

### Monitoring
- Log all authentication attempts
- Monitor for suspicious activities
- Set up alerts for errors and security events
- Regularly review logs and access patterns

## Troubleshooting

### Secret Key Error
**Problem**: `ImproperlyConfigured: DJANGO_SECRET_KEY must be set...`

**Solution**: 
1. Generate a new secret key
2. Set it in the `.env` file
3. Restart the application

### Google OAuth Errors
**Problem**: Google authentication not working

**Solution**:
1. Verify `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set
2. Check Google OAuth console for correct redirect URI
3. Ensure domain is whitelisted in Google settings
4. Check browser console for CORS errors

### CORS Errors
**Problem**: Frontend can't reach backend API

**Solution**:
1. Verify `DJANGO_CORS_ALLOWED_ORIGINS` includes frontend URL
2. Ensure URL protocol matches (https://)
3. Check `DJANGO_CSRF_TRUSTED_ORIGINS`
4. Verify DNS records

## Support

For issues or questions, refer to:
- Django Documentation: https://docs.djangoproject.com/
- Google OAuth: https://developers.google.com/identity/protocols/oauth2
- Deployment Security: https://docs.djangoproject.com/en/stable/howto/deployment/checklist/
