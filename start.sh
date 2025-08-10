#!/bin/bash

echo "🚀 Starting Railway deployment..."

# Aspetta che i database siano pronti
echo "⏳ Waiting for databases to be ready..."
python manage.py wait_for_db || exit 1

# Esegui le migrazioni
echo "📊 Running migrations..."
python manage.py migrate --verbosity=2 || exit 1
python manage.py migrate --database=goldbet_db --verbosity=2 || exit 1
python manage.py migrate --database=better_db --verbosity=2 || exit 1

# Setup agenzie e utenti
echo "🏢 Setting up agencies and users..."
python manage.py setup_agenzie --create-agenzie --create-users || echo "Setup users failed, continuing..."

# Avvia il server
echo "🌟 Starting web server..."
exec gunicorn agenzia.wsgi --bind 0.0.0.0:$PORT --log-file -