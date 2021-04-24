import httpx

import logging

log = logging.getLogger(__name__)


def get(url, *args, n_tries_: int = 3, **kwargs):
    """httpx GET with default retries"""
    for i in range(n_tries_):
        try:
            res = httpx.get(url, *args, **kwargs)
            res.raise_for_status()
            return res
        except Exception as e:
            if i == n_tries_ - 1:
                raise e
            log.debug(f'Error on http GET:({e.__class__.__name__}){e}', exc_info=True)


def post(url, *args, n_tries_: int = 3, **kwargs):
    """httpx POST with default retries"""
    for i in range(n_tries_):
        try:
            res = httpx.post(url, *args, **kwargs)
            res.raise_for_status()
            return res
        except Exception as e:
            if i == n_tries_ - 1:
                raise e
            log.debug(f'Error on http POST:({e.__class__.__name__}){e}', exc_info=True)
