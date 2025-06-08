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
    url = os.getenv(
        "CORREIOS_CEP_URL",
        "https://buscacepinter.correios.com.br/app/endereco/carrega-cep-endereco.php",  # NOQA
    )

    def _request(self, cep):
        response = requests.post(self.url, data={
            "pagina": "/app/endereco/index.php",
            "cepaux": "",
            "mensagem_alerta": "",
            "endereco": cep,
            "tipoCEP": "ALL",
        }, headers={
            "Referer": "https://buscacepinter.correios.com.br/app/endereco/index.php?t",
        }, timeout=10)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as ex:
            logger.exception('Erro no site dos Correios')
            raise ex
        return response.json()

    def track(self, cep):
        data = self._request(cep)
        result = []

        found = False
        now = datetime.now()
        
        logger.info("Resposta da API dos Correios: %s", data)

        # Verificar diferentes formatos de resposta
        items = []
        if "dados" in data:
            items = data["dados"]
        elif isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Se a resposta é um dict com dados do CEP diretamente
            if 'cep' in data or 'logradouro' in data:
                items = [data]
            # Tentar outras chaves possíveis
            elif 'enderecos' in data:
                items = data['enderecos']
            elif 'resultado' in data:
                items = data['resultado']

        for item in items:
            if item.get('cep') == cep or item.get('cep') == cep.replace('-', ''):
                found = True

            # Adaptar para diferentes formatos de resposta
            result_data = {
                "_meta": {
                    "v_date": now,
                },
                "cep": item.get('cep', cep),
                "bairro": item.get('bairro', item.get('distrito', '')),
                "cidade": item.get('localidade', item.get('cidade', '')),
                "estado": item.get('uf', item.get('estado', '')),
            }
            
            # Logradouro pode vir em diferentes formatos
            logradouro = item.get('logradouroDNEC', item.get('logradouro', ''))
            if ' - ' in logradouro:
                logradouro, complemento = logradouro.split(' - ', 1)
                result_data['complemento'] = complemento.strip(' -')
            result_data['logradouro'] = logradouro

            result.append(result_data)

        if not found:
            result.append({
                'cep': cep,
                '_meta': {
                    "v_date": now,
                    _notfound_key: True,
                },
            })
        return result
