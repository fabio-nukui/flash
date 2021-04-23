import httpx


def get(url, *args, n_tries_: int = 3, **kwargs):
    """httpx GET with default retries"""
    for i in range(n_tries_):
        res = httpx.get(url, *args, **kwargs)
        res.raise_for_status()
        return res
    raise Exception(f'GET failed after {n_tries_} tries')


def post(url, *args, n_tries_: int = 3, **kwargs):
    """httpx POST with default retries"""
    for i in range(n_tries_):
        res = httpx.post(url, *args, **kwargs)
        res.raise_for_status()
        return res
    raise Exception(f'POST failed after {n_tries_} tries')
