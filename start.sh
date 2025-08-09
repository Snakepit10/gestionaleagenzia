#!/bin/bash

echo "🚀 Starting Railway deployment..."

# Aspetta che i database siano pronti
echo "⏳ Waiting for databases to be ready..."
sleep 10

# Esegui le migrazioni
echo "📊 Running migrations..."
python manage.py migrate --verbosity=2
python manage.py migrate --database=goldbet_db --verbosity=2  
python manage.py migrate --database=better_db --verbosity=2

# Setup agenzie e utenti
echo "🏢 Setting up agencies and users..."
python manage.py setup_agenzie --create-agenzie --create-users

# Avvia il server
echo "🌟 Starting web server..."
exec gunicorn agenzia.wsgi --log-file -