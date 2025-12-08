# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Postmon is a Brazilian CEP (postal code) API service built with Python 3, Bottle framework, and MongoDB. The application provides REST APIs for:

- CEP (postal code) lookup with fallback APIs (ViaCEP -> BrasilAPI)
- Geographic coordinates via Google Maps Geocoding API
- IBGE city/state data integration
- Background task scheduling with Celery

## Architecture

The codebase follows a modular structure:

- **PostmonServer.py**: Main Bottle web server with REST API routes
- **CepTracker.py**: CEP lookup logic with multiple API fallbacks and caching
- **GeoTracker.py**: Geocoding integration with Google Maps API for coordinates
- **IbgeTracker.py**: IBGE data integration for cities/states
- **database.py**: MongoDB connection and data access layer (pymongo 4.x)
- **PostmonTaskScheduler.py**: Celery-based background task scheduler
- **utils.py**: Common utilities (CORS, slugify, etc.)

The application uses MongoDB for caching CEP lookups and storing IBGE data, with configurable expiration times (10 minutes for notfound records, 6 months for valid records).

## Development Setup with UV

This project uses [UV](https://docs.astral.sh/uv/) for fast Python package management.

### Initial Setup
```powershell
# Create virtual environment
py -m uv venv

# Activate (PowerShell)
.\.venv\Scripts\Activate.ps1

# Activate (CMD)
.venv\Scripts\activate.bat

# Install dependencies
py -m uv pip install -r requirements.txt --python .\.venv\Scripts\python.exe

# Install dev dependencies
py -m uv pip install -r requirements-dev.txt --python .\.venv\Scripts\python.exe
```

### Common Development Commands

#### Testing
```bash
pytest                      # Run all tests
pytest test/ -v             # Run tests with verbose output
pytest --cov=.              # Run tests with coverage
flake8                      # Run linting
```

#### Running the Application
```bash
# Local development (port 9876)
python PostmonServer.py

# Interactive mode
ipython -i PostmonServer.py
>> _standalone()

# Background scheduler
celery -A PostmonTaskScheduler worker -B -l info
```

#### Docker
```bash
docker build -t postmon .
docker run -d -p 80:9876 postmon

# Or with docker-compose
docker-compose up -d
```

## Environment Variables

### MongoDB Configuration
- `POSTMON_DB_HOST`: MongoDB host (default: localhost)
- `POSTMON_DB_PORT`: MongoDB port (default: 27017)
- `POSTMON_DB_NAME`: Database name (default: postmon)
- `POSTMON_DB_USER`: MongoDB username
- `POSTMON_DB_PASSWORD`: MongoDB password

### Geocoding Configuration (Google Maps)
- `GOOGLE_MAPS_API_KEY`: Google Maps Geocoding API key (enables coordinate lookup)
- `GEOCODING_BATCH_SIZE`: Number of CEPs to process per batch task (default: 100)

### Monitoring
- `SENTRY_DSN`: Sentry DSN for error tracking (optional)

## Key Dependencies

- **bottle**: Web framework
- **pymongo**: MongoDB driver (4.x)
- **celery**: Background task queue (5.x)
- **requests**: HTTP client for external APIs
- **sentry-sdk**: Error tracking
- **python-slugify**: URL slug generation
- **flake8**: Code linting
- **pytest**: Testing framework

## API Structure

- `/v1/cep/{cep}`: CEP lookup with IBGE city/state info and coordinates
- `/v1/uf/{sigla-uf}`: State information
- `/v1/cidade/{sigla-uf}/{nome-cidade}`: City information
- `/__health__`: Health check endpoint

The CEP lookup implements intelligent fallback between ViaCEP and BrasilAPI, with MongoDB caching and detailed logging for debugging connectivity issues.

### CEP Response with Coordinates

When `GOOGLE_MAPS_API_KEY` is configured, CEP responses include geographic coordinates:

```json
{
  "cep": "01310100",
  "logradouro": "Avenida Paulista",
  "bairro": "Bela Vista",
  "cidade": "Sao Paulo",
  "estado": "SP",
  "latitude": -23.5614,
  "longitude": -46.6558,
  "estado_info": { ... },
  "cidade_info": { ... }
}
```

### Geocoding Background Task

The `geocode_existing_ceps` Celery task processes existing CEPs without coordinates:
- Runs every 6 hours automatically
- Processes 100 CEPs per batch (configurable via `GEOCODING_BATCH_SIZE`)
- Respects Google API rate limits (50ms delay between requests)
- Marks failed geocoding attempts to avoid retrying

## Python Version

**Required**: Python 3.10+

This project was migrated from Python 2.7 to Python 3. Key changes:
- pymongo 4.x (uses `update_one`, `count_documents`, URI authentication)
- sentry-sdk (replaced raven)
- python-slugify (replaced unicode_slugify)
- celery 5.x
- pytest (replaced nose)

## Docker Configuration

### Dockerfile for Python 3
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 9876
CMD ["python", "PostmonServer.py"]
```
