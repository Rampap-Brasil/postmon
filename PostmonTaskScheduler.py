#!/usr/bin/env python
# -*- coding: utf-8 -*-
from datetime import timedelta
import time
from celery import Celery
from celery.utils.log import get_task_logger
from IbgeTracker import IbgeTracker
from GeoTracker import GeoTracker
from database import MongoDB as Database
import os

USERNAME = os.environ.get('POSTMON_DB_USER')
PASSWORD = os.environ.get('POSTMON_DB_PASSWORD')
HOST = os.environ.get('POSTMON_DB_HOST', 'localhost')
PORT = os.environ.get('POSTMON_DB_PORT', '27017')

if all((USERNAME, PASSWORD)):
    broker_conn_string = 'mongodb://%s:%s@%s:%s' \
        % (USERNAME, PASSWORD, HOST, PORT)
else:
    broker_conn_string = 'mongodb://%s:%s' % (HOST, PORT)

print(broker_conn_string)

app = Celery('postmon', broker=broker_conn_string)

app.conf.update(
    CELERY_TASK_SERIALIZER='json',
    CELERY_ACCEPT_CONTENT=['json'],  # Ignore other content
    CELERY_RESULT_SERIALIZER='json',
    CELERY_TIMEZONE='America/Sao_Paulo',
    CELERY_ENABLE_UTC=True,
    CELERYBEAT_SCHEDULE={
        'track_ibge_daily': {
            'task': 'PostmonTaskScheduler.track_ibge',
            'schedule': timedelta(days=1)
        },
        'geocode_existing_ceps': {
            'task': 'PostmonTaskScheduler.geocode_existing_ceps',
            'schedule': timedelta(hours=6),
        }
    }
)

logger = get_task_logger(__name__)


@app.task
def track_ibge():
    logger.info('Iniciando tracking do IBGE...')
    db = Database()
    ibge = IbgeTracker()
    ibge.track(db)
    logger.info('Finalizou o tracking do IBGE')


@app.task
def geocode_existing_ceps(batch_size=None):
    """
    Geocodifica CEPs existentes que nao possuem coordenadas.

    Processa em batches para respeitar rate limits da API do Google.
    Utiliza delay entre requisicoes para evitar OVER_QUERY_LIMIT.

    Args:
        batch_size: Numero de CEPs a processar por execucao.
                   Default: variavel de ambiente GEOCODING_BATCH_SIZE ou 100.
    """
    if batch_size is None:
        batch_size = int(os.environ.get('GEOCODING_BATCH_SIZE', 100))

    logger.info('Iniciando geocodificacao de CEPs existentes (batch_size=%d)...',
                batch_size)

    db = Database()
    geo = GeoTracker()

    if not geo.enabled:
        logger.warning('Geocodificacao desabilitada. '
                      'Configure GOOGLE_MAPS_API_KEY para habilitar.')
        return {
            'processed': 0,
            'success': 0,
            'failed': 0,
            'message': 'Geocoding disabled'
        }

    # Buscar CEPs sem coordenadas
    ceps_pendentes = db.find_ceps_without_coordinates(limit=batch_size)
    logger.info('Encontrados %d CEPs pendentes de geocodificacao',
                len(ceps_pendentes))

    stats = {'processed': 0, 'success': 0, 'failed': 0}

    for record in ceps_pendentes:
        cep = record.get('cep', '')
        logger.info('Geocodificando CEP: %s', cep)

        try:
            result = geo.geocode(
                logradouro=record.get('logradouro', ''),
                bairro=record.get('bairro', ''),
                cidade=record.get('cidade', ''),
                estado=record.get('estado', '')
            )

            if result:
                if result.get('latitude') is not None:
                    db.update_coordinates(
                        cep=cep,
                        latitude=result['latitude'],
                        longitude=result['longitude'],
                        geo_source=result.get('geo_source', 'google_maps'),
                        geo_status='success'
                    )
                    stats['success'] += 1
                    logger.info('CEP %s geocodificado: lat=%s, lng=%s',
                               cep, result['latitude'], result['longitude'])
                else:
                    # Marcar como falha para nao tentar novamente
                    db.mark_geocoding_failed(
                        cep=cep,
                        geo_status=result.get('status', 'not_found'),
                        geo_source=result.get('geo_source', 'google_maps')
                    )
                    stats['failed'] += 1
                    logger.info('CEP %s: geocodificacao falhou (status=%s)',
                               cep, result.get('status'))

            stats['processed'] += 1

            # Rate limit: aguardar 50ms entre requisicoes
            # Google permite 50 req/s, usamos 20 req/s para margem
            time.sleep(0.05)

        except Exception as ex:
            logger.error('Erro ao geocodificar CEP %s: %s', cep, ex)
            stats['failed'] += 1
            stats['processed'] += 1

    # Log estatisticas finais
    logger.info('Geocodificacao finalizada: %d processados, %d sucesso, %d falhas',
                stats['processed'], stats['success'], stats['failed'])

    # Log estatisticas gerais do banco
    total_stats = db.get_geocoding_stats()
    logger.info('Estatisticas gerais: %d/%d geocodificados (%.1f%%)',
                total_stats['geocoded'], total_stats['total'],
                total_stats['percentage'])

    return stats
