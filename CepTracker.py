#!/usr/bin/env python
# -*- coding: utf-8 -*-
from datetime import datetime
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)
_notfound_key = '__notfound__'

# Configurar logging para debug
logging.basicConfig(level=logging.INFO)


class CepTracker(object):
    # APIs alternativas para consulta de CEP
    apis = [
        {
            'name': 'ViaCEP',
            'url': 'https://viacep.com.br/ws/{}/json/',
            'timeout': 10
        },
        {
            'name': 'PostalPinCode',
            'url': 'https://api.postalpincode.in/pincode/{}',
            'timeout': 10
        },
        {
            'name': 'CEP.la',
            'url': 'https://cep.la/{}',
            'timeout': 10
        }
    ]

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
        return {
            'cep': data.get('cep', ''),
            'logradouro': data.get('street', ''),
            'complemento': '',
            'bairro': data.get('district', ''),
            'localidade': data.get('city', ''),
            'uf': data.get('state', ''),
            'ibge': data.get('city_ibge', '')
        }

    def _request_cepaberto(self, cep):
        """Consultar CEP Aberto como alternativa"""
        clean_cep = cep.replace('-', '').replace('.', '')
        url = 'https://www.cepaberto.com/api/v3/cep?cep={}'.format(clean_cep)
        
        logger.info("Tentando CEP Aberto: %s", url)
        
        headers = {
            'Authorization': 'Token token=',  # Precisaria de token
            'User-Agent': 'Postmon/1.0'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Converter formato CEP Aberto para ViaCEP
        return {
            'cep': data.get('cep', ''),
            'logradouro': data.get('address', ''),
            'complemento': '',
            'bairro': data.get('district', ''),
            'localidade': data.get('city', {}).get('name', ''),
            'uf': data.get('state', {}).get('code', ''),
        }

    def _request(self, cep):
        clean_cep = cep.replace('-', '').replace('.', '')
        
        logger.info("=== DEBUG CepTracker ===")
        logger.info("CEP original: %s", cep)
        logger.info("CEP limpo: %s", clean_cep)
        
        # Lista de métodos para tentar em ordem
        methods = [
            ('ViaCEP', self._request_viacep),
            ('BrasilAPI', self._request_brasilapi),
            # ('CEPAberto', self._request_cepaberto),  # Desabilitado - precisa token
        ]
        
        last_error = None
        
        for api_name, method in methods:
            try:
                logger.info("Tentando API: %s", api_name)
                data = method(clean_cep)
                logger.info("Sucesso com %s: %s", api_name, data)
                return data
                
            except requests.exceptions.ConnectTimeout as ex:
                last_error = ex
                logger.error('Timeout na API %s: %s', api_name, ex)
                continue
                
            except requests.exceptions.ConnectionError as ex:
                last_error = ex
                logger.error('Erro de conexão na API %s: %s', api_name, ex)
                continue
                
            except requests.exceptions.HTTPError as ex:
                last_error = ex
                logger.error('Erro HTTP na API %s: %s', api_name, ex)
                continue
                
            except requests.exceptions.RequestException as ex:
                last_error = ex
                logger.error('Erro de requisição na API %s: %s', api_name, ex)
                continue
                
            except Exception as ex:
                last_error = ex
                logger.error('Erro geral na API %s: %s', api_name, ex)
                continue
        
        # Se todas as APIs falharam, relançar último erro
        logger.error('Todas as APIs falharam. Último erro: %s', last_error)
        raise last_error

    def track(self, cep):
        logger.info("=== INICIANDO TRACK CEP: %s ===", cep)
        
        try:
            data = self._request(cep)
            logger.info("Dados recebidos da API: %s", data)
            
        except Exception as ex:
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
            
            # Verificar se bairro está vazio ou em branco
            bairro = data.get('bairro', '').strip()
            if not bairro:
                logger.info("CEP com bairro em branco, marcando como not found")
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
                    "logradouro": data.get('logradouro', ''),
                    "bairro": bairro,
                    "cidade": data.get('localidade', ''),
                    "estado": data.get('uf', ''),
                }
                
                # Complemento da API
                if data.get('complemento'):
                    result_data['complemento'] = data.get('complemento')
                    
                logger.info("Dados processados: %s", result_data)
                result.append(result_data)

        logger.info("=== RESULTADO FINAL: %s ===", result)
        return result
