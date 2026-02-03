#!/usr/bin/env python
# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import logging

import requests

from GeoTracker import GeoTracker

logger = logging.getLogger(__name__)
_notfound_key = '__notfound__'

# Configurar logging para debug
logging.basicConfig(level=logging.INFO)


class CircuitBreaker:
    """
    Implementa o padrão Circuit Breaker para APIs externas.
    Desabilita temporariamente APIs que estão falhando para evitar
    tentativas desnecessárias.
    """
    # Estado compartilhado entre todas as instâncias
    _circuits = {}

    # Configurações
    FAILURE_THRESHOLD = 3  # Falhas consecutivas para abrir o circuito
    RECOVERY_TIMEOUT = 300  # 5 minutos para tentar novamente

    @classmethod
    def is_open(cls, api_name):
        """Verifica se o circuito está aberto (API desabilitada)"""
        if api_name not in cls._circuits:
            return False

        circuit = cls._circuits[api_name]
        if circuit['failures'] < cls.FAILURE_THRESHOLD:
            return False

        # Verificar se já passou o tempo de recuperação
        if datetime.now() >= circuit['retry_after']:
            logger.info("CircuitBreaker: Tentando reconectar %s após timeout", api_name)
            return False

        return True

    @classmethod
    def record_success(cls, api_name):
        """Registra sucesso - reseta o contador de falhas"""
        if api_name in cls._circuits:
            logger.info("CircuitBreaker: %s recuperada, resetando contador", api_name)
            del cls._circuits[api_name]

    @classmethod
    def record_failure(cls, api_name):
        """Registra falha - incrementa contador"""
        if api_name not in cls._circuits:
            cls._circuits[api_name] = {
                'failures': 0,
                'retry_after': datetime.now()
            }

        cls._circuits[api_name]['failures'] += 1
        failures = cls._circuits[api_name]['failures']

        if failures >= cls.FAILURE_THRESHOLD:
            cls._circuits[api_name]['retry_after'] = (
                datetime.now() + timedelta(seconds=cls.RECOVERY_TIMEOUT)
            )
            logger.warning(
                "CircuitBreaker: %s desabilitada por %d segundos após %d falhas",
                api_name, cls.RECOVERY_TIMEOUT, failures
            )
        else:
            logger.info("CircuitBreaker: %s falha %d/%d",
                       api_name, failures, cls.FAILURE_THRESHOLD)

    @classmethod
    def get_status(cls):
        """Retorna status de todos os circuitos para debug"""
        return {
            name: {
                'failures': circuit['failures'],
                'is_open': circuit['failures'] >= cls.FAILURE_THRESHOLD,
                'retry_after': circuit['retry_after'].isoformat()
            }
            for name, circuit in cls._circuits.items()
        }


class CepTracker(object):

    def __init__(self):
        """Inicializa o CepTracker com GeoTracker opcional"""
        self.geo_tracker = GeoTracker()
        if self.geo_tracker.enabled:
            logger.info('CepTracker: Geocodificacao habilitada')
        else:
            logger.info('CepTracker: Geocodificacao desabilitada '
                       '(GOOGLE_MAPS_API_KEY nao configurada)')

    def _request_viacep(self, cep):
        """Consultar ViaCEP"""
        clean_cep = cep.replace('-', '').replace('.', '')
        url = 'https://viacep.com.br/ws/{}/json/'.format(clean_cep)

        logger.info("Tentando ViaCEP: %s", url)

        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()

    def _request_brasilapi(self, cep):
        """Consultar BrasilAPI como alternativa"""
        clean_cep = cep.replace('-', '').replace('.', '')
        url = 'https://brasilapi.com.br/api/cep/v1/{}'.format(clean_cep)

        logger.info("Tentando BrasilAPI: %s", url)

        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Converter formato BrasilAPI para ViaCEP
        # BrasilAPI usa: street, neighborhood, city, state
        return {
            'cep': data.get('cep', ''),
            'logradouro': data.get('street', ''),
            'complemento': '',
            'bairro': data.get('neighborhood', ''),
            'localidade': data.get('city', ''),
            'uf': data.get('state', ''),
            'ibge': ''
        }

    def _request(self, cep):
        clean_cep = cep.replace('-', '').replace('.', '')

        logger.info("=== DEBUG CepTracker ===")
        logger.info("CEP original: %s", cep)
        logger.info("CEP limpo: %s", clean_cep)

        # Lista de métodos para tentar em ordem
        # BrasilAPI primeiro (Cloudflare) pois ViaCEP (DigitalOcean) pode estar inacessível
        methods = [
            ('BrasilAPI', self._request_brasilapi),
            ('ViaCEP', self._request_viacep),
        ]

        last_error = None

        for api_name, method in methods:
            # Verificar circuit breaker
            if CircuitBreaker.is_open(api_name):
                logger.info("API %s desabilitada pelo CircuitBreaker, pulando...", api_name)
                continue

            try:
                logger.info("Tentando API: %s", api_name)
                data = method(clean_cep)
                logger.info("Sucesso com %s: %s", api_name, data)
                CircuitBreaker.record_success(api_name)
                return data

            except requests.exceptions.ConnectTimeout as ex:
                last_error = ex
                logger.error('Timeout na API %s: %s', api_name, ex)
                CircuitBreaker.record_failure(api_name)
                continue

            except requests.exceptions.ConnectionError as ex:
                last_error = ex
                logger.error('Erro de conexão na API %s: %s', api_name, ex)
                CircuitBreaker.record_failure(api_name)
                continue

            except requests.exceptions.HTTPError as ex:
                # HTTP 404 = CEP não encontrado - não tentar outra API
                if ex.response is not None and ex.response.status_code == 404:
                    logger.info('CEP não encontrado na API %s (404)', api_name)
                    CircuitBreaker.record_success(api_name)
                    raise  # Propagar 404 para ser tratado em track()

                # Outros HTTP errors (5xx, etc) - tentar próxima API
                last_error = ex
                logger.error('Erro HTTP na API %s: %s', api_name, ex)
                continue

            except requests.exceptions.RequestException as ex:
                last_error = ex
                logger.error('Erro de requisição na API %s: %s', api_name, ex)
                CircuitBreaker.record_failure(api_name)
                continue

            except Exception as ex:
                last_error = ex
                logger.error('Erro geral na API %s: %s', api_name, ex)
                continue

        # Se todas as APIs falharam, relançar último erro
        logger.error('Todas as APIs falharam. Último erro: %s', last_error)
        if last_error is not None:
            raise last_error
        # Se não há último erro, significa que todas as APIs estão no circuit breaker
        # Isso é diferente de "CEP não encontrado" - é uma indisponibilidade temporária
        raise requests.exceptions.ConnectionError('Todas as APIs indisponiveis (circuit breaker)')

    def track(self, cep):
        logger.info("=== INICIANDO TRACK CEP: %s ===", cep)

        try:
            data = self._request(cep)
            logger.info("Dados recebidos da API: %s", data)

        except requests.exceptions.ConnectionError as ex:
            # ConnectionError inclui circuit breaker - re-raise para 503
            logger.error('Erro de conexão ao consultar CEP %s: %s', cep, ex)
            raise

        except requests.exceptions.HTTPError as ex:
            # HTTP 404 = CEP não encontrado na API
            if ex.response is not None and ex.response.status_code == 404:
                logger.info('CEP %s não encontrado na API (404)', cep)
                return [{
                    'cep': cep,
                    '_meta': {
                        "v_date": datetime.now(),
                        _notfound_key: True,
                    },
                }]
            # Outros erros HTTP - re-raise para 503
            logger.error('Erro HTTP ao consultar CEP %s: %s', cep, ex)
            raise

        except Exception:
            logger.exception('Erro ao consultar CEP: %s', cep)
            return [{
                'cep': cep,
                '_meta': {
                    "v_date": datetime.now(),
                    _notfound_key: True,
                },
            }]

        result = []
        now = datetime.now()

        # Verificar se API retornou erro
        if data.get('erro') or not data.get('localidade'):
            logger.info("CEP não encontrado na API")
            result.append({
                'cep': cep,
                '_meta': {
                    "v_date": now,
                    _notfound_key: True,
                },
            })
        else:
            logger.info("CEP encontrado, processando dados")

            # Verificar se bairro e logradouro estão vazios
            bairro = data.get('bairro', '').strip()
            logradouro = data.get('logradouro', '').strip()

            if not bairro and not logradouro:
                # CEP sem bairro E sem logradouro é considerado incompleto
                logger.info("CEP sem bairro e sem logradouro, marcando como not found")
                result.append({
                    'cep': cep,
                    '_meta': {
                        "v_date": now,
                        _notfound_key: True,
                    },
                })
            else:
                # Converter formato da API para formato Postmon
                result_data = {
                    "_meta": {
                        "v_date": now,
                    },
                    "cep": data.get('cep', cep).replace('-', ''),
                    "logradouro": logradouro,
                    "bairro": bairro,
                    "cidade": data.get('localidade', ''),
                    "estado": data.get('uf', ''),
                }

                # Complemento da API
                if data.get('complemento'):
                    result_data['complemento'] = data.get('complemento')

                # Geocodificacao: obter coordenadas do endereco
                if self.geo_tracker.enabled:
                    logger.info("Iniciando geocodificacao do endereco")
                    geo_result = self.geo_tracker.geocode(
                        logradouro=result_data.get('logradouro', ''),
                        bairro=result_data.get('bairro', ''),
                        cidade=result_data.get('cidade', ''),
                        estado=result_data.get('estado', '')
                    )
                    if geo_result:
                        if geo_result.get('latitude') is not None:
                            result_data['latitude'] = geo_result['latitude']
                            result_data['longitude'] = geo_result['longitude']
                            logger.info("Coordenadas obtidas: lat=%s, lng=%s",
                                       result_data['latitude'],
                                       result_data['longitude'])
                        # Salvar metadados de geocodificacao
                        result_data['_meta']['geo_source'] = geo_result.get('geo_source')
                        result_data['_meta']['geo_status'] = geo_result.get('status')
                        result_data['_meta']['geo_date'] = geo_result.get('geo_date')

                logger.info("Dados processados: %s", result_data)
                result.append(result_data)

        logger.info("=== RESULTADO FINAL: %s ===", result)
        return result
