# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Postmon is a Brazilian CEP (postal code) and tracking API service built with Python, Bottle framework, and MongoDB. The application provides REST APIs for:

- CEP (postal code) lookup with fallback APIs (ViaCEP → BrasilAPI)
- Package tracking integration
- IBGE city/state data integration
- Background task scheduling with Celery

## Architecture

The codebase follows a modular structure:

- **PostmonServer.py**: Main Bottle web server with REST API routes
- **CepTracker.py**: CEP lookup logic with multiple API fallbacks and caching
- **PackTracker.py**: Package tracking functionality
- **IbgeTracker.py**: IBGE data integration for cities/states
- **database.py**: MongoDB connection and data access layer
- **PostmonTaskScheduler.py**: Celery-based background task scheduler
- **utils.py**: Common utilities (CORS, slugify, etc.)

The application uses MongoDB for caching CEP lookups and storing IBGE data, with configurable expiration times (10 minutes for notfound records, 6 months for valid records).

## Common Development Commands

### Testing
```bash
make test          # Run tests with PEP8 checks
make coverage      # Run tests with coverage reports
make pep8          # Run only PEP8/flake8 checks
nosetests          # Run tests directly
```

### Running the Application
```bash
# Local development (port 9876)
python PostmonServer.py

# Interactive mode
ipython -i PostmonServer.py
>> _standalone()

# Background scheduler
celery worker -B -A PostmonTaskScheduler -l info
```

### Docker
```bash
docker build -t postmon .
docker run -d -p 80:9876 postmon

# Or with docker-compose
docker-compose up -d
```

## Environment Variables

Required for MongoDB authentication:
- `POSTMON_DB_HOST`: MongoDB host (default: localhost)
- `POSTMON_DB_PORT`: MongoDB port (default: 27017)
- `POSTMON_DB_NAME`: Database name (default: postmon)
- `POSTMON_DB_USER`: MongoDB username
- `POSTMON_DB_PASSWORD`: MongoDB password

## Key Dependencies

- bottle: Web framework
- pymongo: MongoDB driver
- celery: Background task queue
- requests: HTTP client for external APIs
- flake8: Code linting
- nose: Testing framework

## API Structure

- `/v1/cep/{cep}`: CEP lookup with IBGE city/state info
- `/uf/{sigla-uf}`: State information
- `/cidade/{sigla-uf}/{nome-cidade}`: City information
- `/__health__`: Health check endpoint

The CEP lookup implements intelligent fallback between ViaCEP and BrasilAPI, with MongoDB caching and detailed logging for debugging connectivity issues.