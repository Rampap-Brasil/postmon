def expired(record_date):
    _meta = record_date.get('_meta', {})
    v_date = _meta.get('v_date') or record_date.get('v_date')
    if not v_date:
        return True

    if _notfound(record_date):
        # Para registros "not found", expirar em 10 minutos para desenvolvimento
        MINUTES = 10
        now = datetime.now()
        is_expired = (now - v_date >= timedelta(minutes=MINUTES))
        logger.info("Registro notfound, idade: %s, expirou: %s", now - v_date, is_expired)
        return is_expired
    else:
        # Para registros válidos, manter 6 meses
        WEEKS = 26
        now = datetime.now()
        return (now - v_date >= timedelta(weeks=WEEKS))