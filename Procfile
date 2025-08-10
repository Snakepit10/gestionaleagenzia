web: python manage.py migrate && python manage.py init_railway && python manage.py collectstatic --noinput && gunicorn agenzia.wsgi --bind 0.0.0.0:$PORT --workers 1 --timeout 120 --log-level info
