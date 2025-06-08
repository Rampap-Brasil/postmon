#!/usr/bin/env python
# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import os
import bottle
import json
import logging
import xmltodict
from bottle import run, request, response, template, HTTPResponse
from bottle.ext.healthcheck import HealthCheck
from raven import Client
from raven.contrib.bottle import Sentry

from CepTracker import CepTracker, _notfound_key
import PackTracker
import requests
from database import MongoDB as Database
from utils import EnableCORS

logger = logging.getLogger(__name__)
HealthCheck(bottle, "/__health__")

app = bottle.default_app()
app.catchall = False
app_v1 = bottle.Bottle()
app_v1.catchall = False
jsonp_query_key = 'callback'

db = Database()
db.create_indexes()


def validate_format(callback):
    def wrapper(*args, **kwargs):
        output_format = request.query.format
        if output_format and output_format not in {'json', 'jsonp', 'xml'}:
            message = "400 Parametro format='%s' invalido." % output_format
            return make_error(message, output_format='json')
        return callback(*args, **kwargs)
    return wrapper


def _notfound(record):
    _meta = record.get('_meta', {})
    return _notfound_key in _meta or _notfound_key in record


def expired(record_date):
    _meta = record_date.get('_meta', {})
    v_date = _meta.get('v_date') or record_date.get('v_date')
    if not v_date:
        return True

    if _notfound(record_date):
        # Para registros "not found", expirar em 1 hora para tentar novamente
        HOURS = 1
        now = datetime.now()
        is_expired = (now - v_date >= timedelta(hours=HOURS))
        logger.info("Registro notfound, idade: %s, expirou: %s", now - v_date, is_expired)
        return is_expired
    else:
        # Para registros válidos, manter 6 meses
        WEEKS = 26
        now = datetime.now()
        return (now - v_date >= timedelta(weeks=WEEKS))


def _get_info_from_source(cep):
    logger.info("=== CHAMANDO CepTracker.track para CEP: %s ===", cep)
    tracker = CepTracker()
    return tracker.track(cep)


def format_result(result):
    logger.info("=== FORMAT_RESULT chamado com: %s ===", result)
    # checa se foi solicitada resposta em JSONP
    js_func_name = bottle.request.query.get(jsonp_query_key)

    # checa se foi solicitado xml
    format = bottle.request.query.get('format')
    if format == 'xml':
        response.content_type = 'application/xml'
        return xmltodict.unparse({'result': result})

    if js_func_name:
        # se a resposta vai ser JSONP, o content type deve ser js e seu
        # conteudo deve ser JSON
        response.content_type = 'application/javascript'
        result = json.dumps(result)

        result = '%s(%s);' % (js_func_name, result)
    return result


def make_error(message, output_format=None):
    logger.info("=== MAKE_ERROR chamado: %s ===", message)
    formats = {
        'json': 'application/json',
        'xml': 'application/xml',
        'jsonp': 'application/javascript',
    }
    format_ = output_format or bottle.request.query.get('format', 'json')
    response = HTTPResponse(status=message, content_type=formats[format_])
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


def _get_estado_info(db, sigla):
    sigla = sigla.upper()
    return db.get_one_uf(sigla, fields={'_id': False, 'sigla': False})


def _get_cidade_info(db, sigla_uf, nome_cidade):
    fields = {
        '_id': False,
        'sigla_uf': False,
        'codigo_ibge_uf': False,
        'sigla_uf_nome_cidade': False,
        'nome': False
    }
    return db.get_one_cidade(sigla_uf, nome_cidade, fields=fields)


# REGEX CORRIGIDO - Aceita CEP com ou sem hífen, mais flexível
@app.route('/cep/<cep:re:[0-9]{5}-?[0-9]{3}>')
@app_v1.route('/cep/<cep:re:[0-9]{5}-?[0-9]{3}>')
def verifica_cep(cep):
    logger.info("=== ROTA CEP CHAMADA: %s ===", cep)
    cep_limpo = cep.replace('-', '')
    logger.info("CEP limpo: %s", cep_limpo)
    
    db = Database()
    response.headers['Access-Control-Allow-Origin'] = '*'
    message = None
    
    logger.info("Consultando cache no MongoDB...")
    result = db.get_one(cep_limpo, fields={'_id': False})
    logger.info("Resultado do cache: %s", result)
    
    if not result or expired(result):
        logger.info("Cache vazio ou expirado, consultando fonte externa...")
        result = None
        try:
            info = _get_info_from_source(cep_limpo)
            logger.info("Info recebida da fonte: %s", info)
        except requests.exceptions.RequestException as ex:
            message = '503 Servico Temporariamente Indisponivel'
            logger.exception(message)
            return make_error(message)
        except Exception as ex:
            message = '500 Erro interno'
            logger.exception("Erro geral: %s", ex)
            return make_error(message)
        else:
            logger.info("Salvando dados no MongoDB...")
            for item in info:
                logger.info("Salvando item: %s", item)
                db.insert_or_update(item)
            result = db.get_one(cep_limpo, fields={
                '_id': False, 'v_date': False})
            logger.info("Resultado após salvar: %s", result)

    if result:
        notfound = _notfound(result)
        logger.info("Resultado encontrado, notfound=%s", notfound)
    else:
        notfound = True
        logger.info("Nenhum resultado encontrado")

    if notfound:
        message = '404 CEP %s nao encontrado' % cep_limpo
        logger.info("Retornando erro: %s", message)
        return make_error(message)

    logger.info("Processando resultado final...")
    result.pop('v_date', None)
    result.pop('_meta', None)

    response.headers['Cache-Control'] = 'public, max-age=2592000'
    sigla_uf = result['estado']
    estado_info = _get_estado_info(db, sigla_uf)
    if estado_info:
        result['estado_info'] = estado_info
    nome_cidade = result['cidade']
    cidade_info = _get_cidade_info(db, sigla_uf, nome_cidade)
    if cidade_info:
        result['cidade_info'] = cidade_info
    
    logger.info("Retornando resultado final: %s", result)
    return format_result(result)


@app_v1.route('/uf/<sigla>')
def uf(sigla):
    response.headers['Access-Control-Allow-Origin'] = '*'
    db = Database()
    result = _get_estado_info(db, sigla)
    if result:
        response.headers['Cache-Control'] = 'public, max-age=2592000'
        return format_result(result)
    else:
        message = '404 Estado %s nao encontrado' % sigla
        logger.warning(message)
        return make_error(message)


@app_v1.route('/cidade/<sigla_uf>/<nome>')
def cidade(sigla_uf, nome):
    response.headers['Access-Control-Allow-Origin'] = '*'
    db = Database()
    result = _get_cidade_info(db, sigla_uf, nome.decode('utf-8'))
    if result:
        response.headers['Cache-Control'] = 'public, max-age=2592000'
        return format_result(result)
    else:
        message = '404 Cidade %s-%s nao encontrada' % (nome, sigla_uf)
        logger.warning(message)
        return make_error(message)


@app_v1.route('/rastreio/<provider>/<track>')
def track_pack(provider, track):
    response.headers['Access-Control-Allow-Origin'] = '*'
    if provider == 'ect':
        auth = (
            request.headers.get('x-correios-usuario'),
            request.headers.get('x-correios-senha'),
        )
        if auth == (None, None):
            auth = None

        try:
            historico = PackTracker.correios(track, auth=auth)
        except (AttributeError, ValueError):
            message = "404 Pacote %s nao encontrado" % track
            logger.exception(message)
        else:
            return format_result({
                'servico': provider,
                'codigo': track,
                'historico': historico,
            })
    else:
        message = '404 Servico %s nao encontrado' % provider
        logger.warning(message)
    return make_error(message)


@app_v1.route('/rastreio/<token>')
def track_pack_token(token):
    return make_error('404 NOT IMPLEMENTED')


@app_v1.route('/rastreio/<provider>/<track>', method='POST')
def track_pack_register(provider, track):
    """
    Registra o rastreamento do pacote. O `callback` é parâmetro obrigatório,
    qualquer outra informação passada será devolvida quando o `callback` for
    chamado.

    {
        "callback": "http://httpbin.org/post",
        "myid": 1,
        "other": "thing"
    }
    """
    if "callback" not in request.json:
        message = "400 callback obrigatorio"
        return make_error(message)

    try:
        result = PackTracker.register(provider, track, request.json)
    except (AttributeError, ValueError):
        message = "400 Falha no registro do %s/%s" % (provider, track)
        logger.exception(message)
        return make_error(message)
    else:
        return format_result({
            'token': result,
        })


@app.route('/crossdomain.xml')
def crossdomain():
    response.content_type = 'application/xml'
    return template('crossdomain')


app.install(validate_format)
app_v1.install(validate_format)
app.install(EnableCORS())
app_v1.install(EnableCORS())
app.mount('/v1', app_v1)

SENTRY_DSN = os.getenv('SENTRY_DSN')
if SENTRY_DSN:
    sentry_client = Client(SENTRY_DSN)
    app = Sentry(app, sentry_client)
    app_v1 = Sentry(app_v1, sentry_client)


def _standalone(port=9876):
    run(app=app, host='0.0.0.0', port=port)


if __name__ == "__main__":
    _standalone()
