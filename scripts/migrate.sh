#!/bin/bash

# Run Django migrations
echo "Running migrations..."
python manage.py makemigrations
python manage.py migrate

echo "Migrations completed!"

