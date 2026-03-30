web: python manage.py migrate --noinput && gunicorn signal_bot.wsgi:application --bind 0.0.0.0:$PORT --workers 2
