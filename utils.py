import bottle
from slugify import slugify


def slug(value):
    # python-slugify: allow_unicode=False (ASCII only), separator=' ' (keep spaces)
    value = slugify(value, allow_unicode=False, separator=' ')
    return value.upper()


class EnableCORS(object):
    name = 'enable_cors'
    api = 2

    def apply(self, fn, context):
        def _enable_cors(*args, **kwargs):
            # set CORS headers
            bottle.response.headers.update({
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, OPTIONS',
                'Access-Control-Allow-Headers':
                    ', '.join(bottle.request.headers.keys())  # type: ignore[union-attr]
            })
            if bottle.request.method != 'OPTIONS':
                # actual request; reply with the actual response
                return fn(*args, **kwargs)

        return _enable_cors
