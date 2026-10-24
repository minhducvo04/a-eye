"""Shared tunnel authentication; credentials never enter event logs."""
import hmac
import os

from server.logs import event


def authorized(connection):
    expected = os.environ.get('A_EYE_TOKEN', '')
    if not expected:
        return True
    header = connection.headers.get('authorization', '')
    bearer = header[7:] if header.lower().startswith('bearer ') else ''
    return any(hmac.compare_digest(value.encode(), expected.encode())
               for value in (bearer, connection.query_params.get('token', '')))


async def accept_socket(ws):
    if not authorized(ws):
        event('auth_rejected', level='warning')
        await ws.close(code=4401)
        return False
    await ws.accept()
    event('connect')
    return True
