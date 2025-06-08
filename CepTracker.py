#!/usr/bin/env python
# -*- coding: utf-8 -*-
from datetime import datetime
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)
_notfound_key = '__notfound__'


class CepTracker(object):
    # Usar ViaCEP como alternativa gratuita e confiável
    url = os.getenv(
        "CORREIOS_CEP_URL",
        "https://viacep.com.br/ws/{}/json/",  # ViaCEP API
    )

    def _request(self, cep):
        # Limpar CEP (remover hífen)
        clean_cep = cep.replace('-', '').replace('.', '')
        
        # Usar ViaCEP
        url = self.url.format(clean_cep)
        
        response = requests.get(url, timeout=10)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as ex:
            logger.exception('Erro na API de CEP')
            raise ex
        return response.json()

    def track(self, cep):
        try:
            data = self._request(cep)
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
        
        logger.info("Resposta da API de CEP: %s", data)

        # ViaCEP retorna erro se CEP não encontrado
        if data.get('erro'):
            result.append({
                'cep': cep,
                '_meta': {
                    "v_date": now,
                    _notfound_key: True,
                },
            })
        else:
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
                
            result.append(result_data)

        return result
