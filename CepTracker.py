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
    # Usar ViaCEP como alternativa gratuita e confiável
    url = os.getenv(
        "CORREIOS_CEP_URL",
        "https://viacep.com.br/ws/{}/json/",  # ViaCEP API
    )

    def _request(self, cep):
        # Limpar CEP (remover hífen)
        clean_cep = cep.replace('-', '').replace('.', '')
        
        logger.info("=== DEBUG CepTracker ===")
        logger.info("CEP original: %s", cep)
        logger.info("CEP limpo: %s", clean_cep)
        
        # Usar ViaCEP
        url = self.url.format(clean_cep)
        logger.info("URL da requisição: %s", url)
        
        try:
            response = requests.get(url, timeout=10)
            logger.info("Status da resposta: %s", response.status_code)
            logger.info("Conteúdo da resposta: %s", response.text)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as ex:
            logger.error('Erro HTTP na API de CEP: %s', ex)
            raise ex
        except requests.exceptions.RequestException as ex:
            logger.error('Erro de conexão na API de CEP: %s', ex)
            raise ex
        except Exception as ex:
            logger.error('Erro geral na API de CEP: %s', ex)
            raise ex

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

        # ViaCEP retorna erro se CEP não encontrado
        if data.get('erro'):
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
            # Converter formato ViaCEP para formato Postmon
            result_data = {
                "_meta": {
                    "v_date": now,
                },
                "cep": data.get('cep', cep).replace('-', ''),
                "logradouro": data.get('logradouro', ''),
                "bairro": data.get('bairro', ''),
                "cidade": data.get('localidade', ''),
                "estado": data.get('uf', ''),
            }
            
            # Complemento do ViaCEP
            if data.get('complemento'):
                result_data['complemento'] = data.get('complemento')
                
            logger.info("Dados processados: %s", result_data)
            result.append(result_data)

        logger.info("=== RESULTADO FINAL: %s ===", result)
        return result
