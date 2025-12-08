#!/usr/bin/env python
# -*- coding: utf-8 -*-
from datetime import datetime
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

# Constantes
GEO_SOURCE_GOOGLE = 'google_maps'
GEO_STATUS_SUCCESS = 'success'
GEO_STATUS_NOT_FOUND = 'not_found'
GEO_STATUS_ERROR = 'error'
GEO_STATUS_ZERO_RESULTS = 'zero_results'


class GeoTracker(object):
    """
    Classe para geocodificacao de enderecos usando Google Maps Geocoding API.

    Converte enderecos em coordenadas geograficas (latitude/longitude).
    """

    BASE_URL = 'https://maps.googleapis.com/maps/api/geocode/json'

    def __init__(self, api_key=None):
        """
        Inicializa o GeoTracker.

        Args:
            api_key: Chave da API do Google Maps. Se nao fornecida,
                     busca da variavel de ambiente GOOGLE_MAPS_API_KEY.
        """
        self.api_key = api_key or os.environ.get('GOOGLE_MAPS_API_KEY')
        self.enabled = bool(self.api_key)

        if not self.enabled:
            logger.warning('GeoTracker: GOOGLE_MAPS_API_KEY nao configurada. '
                          'Geocodificacao desabilitada.')

    def _format_address(self, logradouro, bairro, cidade, estado):
        """
        Formata o endereco para consulta na API do Google.

        Args:
            logradouro: Nome da rua/avenida
            bairro: Nome do bairro
            cidade: Nome da cidade
            estado: Sigla do estado (UF)

        Returns:
            String formatada com o endereco completo
        """
        parts = []

        if logradouro:
            parts.append(logradouro)
        if bairro:
            parts.append(bairro)
        if cidade:
            if estado:
                parts.append('{} - {}'.format(cidade, estado))
            else:
                parts.append(cidade)
        elif estado:
            parts.append(estado)

        parts.append('Brasil')

        return ', '.join(parts)

    def _make_request(self, address):
        """
        Faz a requisicao para a API do Google Maps.

        Args:
            address: Endereco formatado para geocodificacao

        Returns:
            dict com a resposta da API ou None em caso de erro
        """
        params = {
            'address': address,
            'key': self.api_key,
            'language': 'pt-BR',
            'region': 'br'
        }

        try:
            logger.info('GeoTracker: Consultando endereco: %s', address)
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            logger.error('GeoTracker: Timeout na requisicao para: %s', address)
            return None

        except requests.exceptions.RequestException as ex:
            logger.error('GeoTracker: Erro na requisicao: %s', ex)
            return None

    def _parse_response(self, data):
        """
        Extrai coordenadas da resposta da API.

        Args:
            data: Resposta JSON da API do Google

        Returns:
            dict com latitude, longitude e status, ou None
        """
        if not data:
            return {
                'status': GEO_STATUS_ERROR,
                'latitude': None,
                'longitude': None
            }

        status = data.get('status', '')

        if status == 'OK':
            results = data.get('results', [])
            if results:
                location = results[0].get('geometry', {}).get('location', {})
                lat = location.get('lat')
                lng = location.get('lng')

                if lat is not None and lng is not None:
                    return {
                        'status': GEO_STATUS_SUCCESS,
                        'latitude': lat,
                        'longitude': lng,
                        'formatted_address': results[0].get('formatted_address', '')
                    }

        elif status == 'ZERO_RESULTS':
            logger.info('GeoTracker: Nenhum resultado encontrado')
            return {
                'status': GEO_STATUS_ZERO_RESULTS,
                'latitude': None,
                'longitude': None
            }

        elif status == 'OVER_QUERY_LIMIT':
            logger.warning('GeoTracker: Limite de requisicoes excedido')
            return {
                'status': GEO_STATUS_ERROR,
                'latitude': None,
                'longitude': None,
                'error': 'rate_limit'
            }

        elif status == 'REQUEST_DENIED':
            logger.error('GeoTracker: Requisicao negada - verificar API key')
            return {
                'status': GEO_STATUS_ERROR,
                'latitude': None,
                'longitude': None,
                'error': 'request_denied'
            }

        return {
            'status': GEO_STATUS_NOT_FOUND,
            'latitude': None,
            'longitude': None
        }

    def geocode(self, logradouro='', bairro='', cidade='', estado=''):
        """
        Geocodifica um endereco e retorna as coordenadas.

        Args:
            logradouro: Nome da rua/avenida
            bairro: Nome do bairro
            cidade: Nome da cidade
            estado: Sigla do estado (UF)

        Returns:
            dict com:
                - latitude: float ou None
                - longitude: float ou None
                - status: 'success', 'not_found', 'zero_results' ou 'error'
                - geo_source: 'google_maps'
                - geo_date: datetime da consulta

            Retorna None se geocodificacao estiver desabilitada.
        """
        if not self.enabled:
            logger.debug('GeoTracker: Geocodificacao desabilitada')
            return None

        # Precisa de pelo menos cidade para geocodificar
        if not cidade:
            logger.warning('GeoTracker: Cidade nao informada, impossivel geocodificar')
            return {
                'status': GEO_STATUS_NOT_FOUND,
                'latitude': None,
                'longitude': None,
                'geo_source': GEO_SOURCE_GOOGLE,
                'geo_date': datetime.now()
            }

        address = self._format_address(logradouro, bairro, cidade, estado)
        data = self._make_request(address)
        result = self._parse_response(data)

        if result:
            result['geo_source'] = GEO_SOURCE_GOOGLE
            result['geo_date'] = datetime.now()

            if result.get('latitude'):
                logger.info('GeoTracker: Coordenadas encontradas: lat=%s, lng=%s',
                           result['latitude'], result['longitude'])

        return result

    def geocode_with_retry(self, logradouro='', bairro='', cidade='', estado='',
                           max_retries=3, delay=1.0):
        """
        Geocodifica com retry em caso de falha.

        Args:
            logradouro, bairro, cidade, estado: Componentes do endereco
            max_retries: Numero maximo de tentativas
            delay: Delay inicial entre tentativas (segundos)

        Returns:
            dict com coordenadas ou None
        """
        result = None
        for attempt in range(max_retries):
            result = self.geocode(logradouro, bairro, cidade, estado)

            if result is None:
                return None

            # Se encontrou coordenadas ou nao tem resultado, retorna
            if result.get('latitude') or result.get('status') in (
                GEO_STATUS_ZERO_RESULTS, GEO_STATUS_NOT_FOUND):
                return result

            # Se erro de rate limit, espera mais tempo
            if result.get('error') == 'rate_limit':
                wait_time = delay * (2 ** attempt)  # Backoff exponencial
                logger.info('GeoTracker: Rate limit, aguardando %s segundos', wait_time)
                time.sleep(wait_time)
                continue

            # Outros erros, tenta novamente com delay
            if result.get('status') == GEO_STATUS_ERROR:
                time.sleep(delay)
                continue

            return result

        logger.warning('GeoTracker: Maximo de tentativas excedido')
        return result


def _standalone():
    """Funcao para testes manuais"""
    logging.basicConfig(level=logging.INFO)

    geo = GeoTracker()

    if not geo.enabled:
        print('Configure GOOGLE_MAPS_API_KEY para testar')
        return

    # Teste com endereco conhecido
    result = geo.geocode(
        logradouro='Avenida Paulista',
        bairro='Bela Vista',
        cidade='Sao Paulo',
        estado='SP'
    )

    print('Resultado:')
    print(result)


if __name__ == '__main__':
    _standalone()
