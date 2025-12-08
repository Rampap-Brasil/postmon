#!/usr/bin/env python
# -*- coding: utf-8 -*-
from datetime import datetime
import os
import re

import pymongo

from utils import slug


class MongoDB(object):

    _fields = [
        'logradouro',
        'bairro',
        'cidade',
        'estado',
        'complemento',
        'latitude',
        'longitude'
    ]

    def __init__(self):
        DATABASE = os.environ.get('POSTMON_DB_NAME', 'postmon')
        HOST = os.environ.get('POSTMON_DB_HOST', 'localhost')
        PORT = int(os.environ.get('POSTMON_DB_PORT', 27017))
        USERNAME = os.environ.get('POSTMON_DB_USER')
        PASSWORD = os.environ.get('POSTMON_DB_PASSWORD')

        # Build connection URI for pymongo 4.x
        if all((USERNAME, PASSWORD)):
            uri = 'mongodb://{}:{}@{}:{}/{}'.format(
                USERNAME, PASSWORD, HOST, PORT, DATABASE)
        else:
            uri = 'mongodb://{}:{}'.format(HOST, PORT)

        self._client = pymongo.MongoClient(uri)
        self._db = self._client[DATABASE]

    def create_indexes(self):
        self._db.ceps.create_index('cep')

    def _fix_kwargs(self, kwargs):
        """Fix kwargs for pymongo 4.x - convert 'fields' to 'projection'"""
        if 'fields' in kwargs:
            kwargs['projection'] = kwargs.pop('fields')
        return kwargs

    def get_one(self, cep, **kwargs):
        kwargs = self._fix_kwargs(kwargs)
        r = self._db.ceps.find_one({'cep': cep}, **kwargs)
        if r and u'endereço' in r and 'endereco' not in r:
            # Garante que o cache também tem a key `endereco`. #92
            # Novos resultados já são adicionados corretamente.
            r['endereco'] = r[u'endereço']
        return r

    def get_one_uf(self, sigla, **kwargs):
        kwargs = self._fix_kwargs(kwargs)
        return self._db.ufs.find_one({'sigla': sigla}, **kwargs)

    def get_one_cidade(self, sigla_uf, nome_cidade, **kwargs):
        def key_func(_uf, _cidade):
            return u'{}_{}'.format(slug(_uf), slug(_cidade))
        sigla_uf_nome_cidade = key_func(sigla_uf, nome_cidade)
        spec = {'sigla_uf_nome_cidade': sigla_uf_nome_cidade}

        search = re.search(r'\((.+)\)', nome_cidade)
        if search:
            nome_cidade_alternativa = search.group(1)
            spec_alternativa = {
                'sigla_uf_nome_cidade': key_func(
                    sigla_uf, nome_cidade_alternativa)
            }
            spec = {'$or': [spec, spec_alternativa]}
        
        kwargs = self._fix_kwargs(kwargs)
        return self._db.cidades.find_one(spec, **kwargs)

    def get_one_uf_by_nome(self, nome, **kwargs):
        kwargs = self._fix_kwargs(kwargs)
        return self._db.ufs.find_one({'nome': nome}, **kwargs)

    def insert_or_update(self, obj, **kwargs):

        update = {'$set': obj}
        empty_fields = set(self._fields) - set(obj)
        if empty_fields:
            update['$unset'] = dict((x, 1) for x in empty_fields)

        self._db.ceps.update_one({'cep': obj['cep']}, update, upsert=True)

    def insert_or_update_uf(self, obj, **kwargs):
        update = {'$set': obj}
        self._db.ufs.update_one({'sigla': obj['sigla']}, update, upsert=True)

    def insert_or_update_cidade(self, obj, **kwargs):
        update = {'$set': obj}
        chave = 'sigla_uf_nome_cidade'
        self._db.cidades.update_one({chave: obj[chave]}, update, upsert=True)

    def remove(self, cep):
        self._db.ceps.delete_one({'cep': cep})

    def find_empty_bairro_records(self):
        """Find all CEP records with empty or missing bairro field"""
        # Query for records where bairro is empty string, null, or missing
        # and exclude records marked as notfound
        query = {
            '$or': [
                {'bairro': ''},
                {'bairro': None},
                {'bairro': {'$exists': False}}
            ],
            '_meta.__notfound__': {'$exists': False}
        }
        return list(self._db.ceps.find(query))

    def cleanup_empty_bairro_records(self, dry_run=True):
        """Remove CEP records with empty bairro field
        
        Args:
            dry_run (bool): If True, only shows what would be deleted without actually deleting
            
        Returns:
            dict: Summary of operation with count and CEPs affected
        """
        # Find records with empty bairro
        records = self.find_empty_bairro_records()
        
        if not records:
            return {
                'count': 0, 
                'ceps': [], 
                'deleted': False,
                'message': 'No records with empty bairro found'
            }
        
        affected_ceps = [record.get('cep', 'unknown') for record in records]
        
        if dry_run:
            return {
                'count': len(records),
                'ceps': affected_ceps,
                'deleted': False,
                'message': 'DRY RUN: These records would be deleted'
            }
        
        # Actually delete the records
        query = {
            '$or': [
                {'bairro': ''},
                {'bairro': None},
                {'bairro': {'$exists': False}}
            ],
            '_meta.__notfound__': {'$exists': False}
        }
        
        result = self._db.ceps.delete_many(query)
        
        return {
            'count': result.deleted_count,
            'ceps': affected_ceps,
            'deleted': True,
            'message': 'Successfully deleted {} records'.format(result.deleted_count)
        }

    def find_ceps_without_coordinates(self, limit=100):
        """
        Busca CEPs validos que nao possuem coordenadas geograficas.

        Args:
            limit: Numero maximo de registros a retornar

        Returns:
            Lista de documentos CEP sem latitude/longitude
        """
        query = {
            '$and': [
                {'$or': [
                    {'latitude': {'$exists': False}},
                    {'latitude': None}
                ]},
                {'_meta.__notfound__': {'$exists': False}}
            ]
        }
        return list(self._db.ceps.find(query).limit(limit))

    def update_coordinates(self, cep, latitude, longitude,
                          geo_source='google_maps', geo_status='success'):
        """
        Atualiza as coordenadas geograficas de um CEP.

        Args:
            cep: Codigo do CEP
            latitude: Latitude em graus decimais
            longitude: Longitude em graus decimais
            geo_source: Fonte das coordenadas (ex: 'google_maps')
            geo_status: Status da geocodificacao ('success', 'not_found', 'error')
        """
        update_data = {
            '_meta.geo_source': geo_source,
            '_meta.geo_status': geo_status,
            '_meta.geo_date': datetime.now()
        }

        if latitude is not None and longitude is not None:
            update_data['latitude'] = latitude
            update_data['longitude'] = longitude

        self._db.ceps.update_one(
            {'cep': cep},
            {'$set': update_data}
        )

    def mark_geocoding_failed(self, cep, geo_status='not_found', geo_source='google_maps'):
        """
        Marca um CEP como geocodificacao falhou (para nao tentar novamente).

        Args:
            cep: Codigo do CEP
            geo_status: Status ('not_found', 'error', 'zero_results')
            geo_source: Fonte tentada
        """
        self._db.ceps.update_one(
            {'cep': cep},
            {'$set': {
                '_meta.geo_source': geo_source,
                '_meta.geo_status': geo_status,
                '_meta.geo_date': datetime.now()
            }}
        )

    def get_geocoding_stats(self):
        """
        Retorna estatisticas de geocodificacao.

        Returns:
            dict com total de CEPs, geocodificados, pendentes e falhas
        """
        # Total de CEPs validos (excluindo notfound)
        total = self._db.ceps.count_documents({'_meta.__notfound__': {'$exists': False}})

        # CEPs com coordenadas
        with_coords = self._db.ceps.count_documents({
            'latitude': {'$exists': True, '$ne': None},
            '_meta.__notfound__': {'$exists': False}
        })

        # CEPs marcados como falha de geocodificacao
        failed = self._db.ceps.count_documents({
            '_meta.geo_status': {'$in': ['not_found', 'error', 'zero_results']},
            '_meta.__notfound__': {'$exists': False}
        })

        # Pendentes = total - com coordenadas - falhas
        pending = total - with_coords - failed

        return {
            'total': total,
            'geocoded': with_coords,
            'failed': failed,
            'pending': max(0, pending),
            'percentage': round((with_coords / float(total) * 100), 2) if total > 0 else 0
        }
