#!/usr/bin/env python
# -*- coding: utf-8 -*-
import unittest
from unittest import mock

import GeoTracker
from GeoTracker import (
    GEO_STATUS_SUCCESS,
    GEO_STATUS_NOT_FOUND,
    GEO_STATUS_ERROR,
    GEO_STATUS_ZERO_RESULTS,
    GEO_SOURCE_GOOGLE
)


class GeoTrackerTest(unittest.TestCase):

    def setUp(self):
        # Criar tracker com API key fake para testes
        self.tracker = GeoTracker.GeoTracker(api_key='fake_api_key')

    def test_init_with_api_key(self):
        """Testa inicializacao com API key"""
        tracker = GeoTracker.GeoTracker(api_key='test_key')
        self.assertTrue(tracker.enabled)
        self.assertEqual(tracker.api_key, 'test_key')

    def test_init_without_api_key(self):
        """Testa inicializacao sem API key"""
        with mock.patch.dict('os.environ', {}, clear=True):
            tracker = GeoTracker.GeoTracker(api_key=None)
            self.assertFalse(tracker.enabled)

    def test_format_address_complete(self):
        """Testa formatacao de endereco completo"""
        address = self.tracker._format_address(
            logradouro='Avenida Paulista',
            bairro='Bela Vista',
            cidade='Sao Paulo',
            estado='SP'
        )
        self.assertEqual(
            address,
            'Avenida Paulista, Bela Vista, Sao Paulo - SP, Brasil'
        )

    def test_format_address_without_logradouro(self):
        """Testa formatacao sem logradouro"""
        address = self.tracker._format_address(
            logradouro='',
            bairro='Centro',
            cidade='Rio de Janeiro',
            estado='RJ'
        )
        self.assertEqual(address, 'Centro, Rio de Janeiro - RJ, Brasil')

    def test_format_address_only_cidade(self):
        """Testa formatacao apenas com cidade"""
        address = self.tracker._format_address(
            logradouro='',
            bairro='',
            cidade='Belo Horizonte',
            estado='MG'
        )
        self.assertEqual(address, 'Belo Horizonte - MG, Brasil')

    def test_format_address_without_estado(self):
        """Testa formatacao sem estado"""
        address = self.tracker._format_address(
            logradouro='Rua A',
            bairro='Centro',
            cidade='Cidade X',
            estado=''
        )
        self.assertEqual(address, 'Rua A, Centro, Cidade X, Brasil')

    @mock.patch('GeoTracker.requests.get')
    def test_geocode_success(self, mock_get):
        """Testa geocodificacao com sucesso"""
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            'status': 'OK',
            'results': [{
                'geometry': {
                    'location': {
                        'lat': -23.5614,
                        'lng': -46.6558
                    }
                },
                'formatted_address': 'Av. Paulista, Bela Vista, Sao Paulo - SP, Brasil'
            }]
        }
        mock_response.raise_for_status = mock.Mock()
        mock_get.return_value = mock_response

        result = self.tracker.geocode(
            logradouro='Avenida Paulista',
            bairro='Bela Vista',
            cidade='Sao Paulo',
            estado='SP'
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['status'], GEO_STATUS_SUCCESS)
        self.assertEqual(result['latitude'], -23.5614)
        self.assertEqual(result['longitude'], -46.6558)
        self.assertEqual(result['geo_source'], GEO_SOURCE_GOOGLE)
        self.assertIn('geo_date', result)

    @mock.patch('GeoTracker.requests.get')
    def test_geocode_zero_results(self, mock_get):
        """Testa geocodificacao sem resultados"""
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            'status': 'ZERO_RESULTS',
            'results': []
        }
        mock_response.raise_for_status = mock.Mock()
        mock_get.return_value = mock_response

        result = self.tracker.geocode(
            logradouro='Endereco Inexistente',
            bairro='Bairro Fake',
            cidade='Cidade Fake',
            estado='XX'
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['status'], GEO_STATUS_ZERO_RESULTS)
        self.assertIsNone(result['latitude'])
        self.assertIsNone(result['longitude'])

    @mock.patch('GeoTracker.requests.get')
    def test_geocode_request_denied(self, mock_get):
        """Testa geocodificacao com requisicao negada"""
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            'status': 'REQUEST_DENIED',
            'error_message': 'Invalid API key'
        }
        mock_response.raise_for_status = mock.Mock()
        mock_get.return_value = mock_response

        result = self.tracker.geocode(
            logradouro='Rua Teste',
            cidade='Sao Paulo',
            estado='SP'
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['status'], GEO_STATUS_ERROR)
        self.assertEqual(result.get('error'), 'request_denied')

    @mock.patch('GeoTracker.requests.get')
    def test_geocode_over_query_limit(self, mock_get):
        """Testa geocodificacao com limite excedido"""
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            'status': 'OVER_QUERY_LIMIT'
        }
        mock_response.raise_for_status = mock.Mock()
        mock_get.return_value = mock_response

        result = self.tracker.geocode(
            logradouro='Rua Teste',
            cidade='Sao Paulo',
            estado='SP'
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['status'], GEO_STATUS_ERROR)
        self.assertEqual(result.get('error'), 'rate_limit')

    @mock.patch('GeoTracker.requests.get')
    def test_geocode_timeout(self, mock_get):
        """Testa geocodificacao com timeout"""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()

        result = self.tracker.geocode(
            logradouro='Rua Teste',
            cidade='Sao Paulo',
            estado='SP'
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['status'], GEO_STATUS_ERROR)

    def test_geocode_without_cidade(self):
        """Testa geocodificacao sem cidade"""
        result = self.tracker.geocode(
            logradouro='Rua Teste',
            bairro='Centro',
            cidade='',
            estado='SP'
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['status'], GEO_STATUS_NOT_FOUND)

    def test_geocode_disabled(self):
        """Testa geocodificacao desabilitada"""
        with mock.patch.dict('os.environ', {}, clear=True):
            tracker = GeoTracker.GeoTracker(api_key=None)
            result = tracker.geocode(
                logradouro='Rua Teste',
                cidade='Sao Paulo',
                estado='SP'
            )
            self.assertIsNone(result)

    @mock.patch('GeoTracker.requests.get')
    @mock.patch('GeoTracker.time.sleep')
    def test_geocode_with_retry_success(self, mock_sleep, mock_get):
        """Testa geocodificacao com retry que sucede"""
        # Primeira chamada: erro, segunda: sucesso
        mock_response_error = mock.Mock()
        mock_response_error.json.return_value = {'status': 'UNKNOWN_ERROR'}
        mock_response_error.raise_for_status = mock.Mock()

        mock_response_success = mock.Mock()
        mock_response_success.json.return_value = {
            'status': 'OK',
            'results': [{
                'geometry': {'location': {'lat': -23.5, 'lng': -46.6}},
                'formatted_address': 'Test'
            }]
        }
        mock_response_success.raise_for_status = mock.Mock()

        mock_get.side_effect = [mock_response_error, mock_response_success]

        result = self.tracker.geocode_with_retry(
            cidade='Sao Paulo',
            estado='SP',
            max_retries=3,
            delay=0.1
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['latitude'], -23.5)


class GeoTrackerParseResponseTest(unittest.TestCase):
    """Testes para o metodo _parse_response"""

    def setUp(self):
        self.tracker = GeoTracker.GeoTracker(api_key='fake_key')

    def test_parse_response_ok(self):
        """Testa parsing de resposta OK"""
        data = {
            'status': 'OK',
            'results': [{
                'geometry': {
                    'location': {'lat': -23.5, 'lng': -46.6}
                },
                'formatted_address': 'Endereco Teste'
            }]
        }

        result = self.tracker._parse_response(data)

        self.assertEqual(result['status'], GEO_STATUS_SUCCESS)
        self.assertEqual(result['latitude'], -23.5)
        self.assertEqual(result['longitude'], -46.6)
        self.assertEqual(result['formatted_address'], 'Endereco Teste')

    def test_parse_response_none(self):
        """Testa parsing de resposta None"""
        result = self.tracker._parse_response(None)
        self.assertEqual(result['status'], GEO_STATUS_ERROR)

    def test_parse_response_empty_results(self):
        """Testa parsing com results vazio"""
        data = {'status': 'OK', 'results': []}
        result = self.tracker._parse_response(data)
        self.assertEqual(result['status'], GEO_STATUS_NOT_FOUND)


if __name__ == '__main__':
    unittest.main()
