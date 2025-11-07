FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && \
    uv pip install --system -r pyproject.toml

# Copy project
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Run migrations
# Note: in production, you should run migrations separately

# Expose port
EXPOSE 8000

# Run the server
CMD ["gunicorn", "server.wsgi:application", "--bind", "0.0.0.0:8000"]

