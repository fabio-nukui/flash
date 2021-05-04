import itertools
import re
import string

from web3 import Web3

sig_pat = re.compile(r'^(?P<fn_name>\w+)(?P<args>\([\w,\[\]]*\))$')


def get_name(signature: str, start_value: str) -> tuple[str, str]:
    assert start_value.startswith('0x')
    assert all(c in string.hexdigits for c in start_value[2:])
    assert 2 < len(start_value) < 11
    match = sig_pat.search(signature)
    if not match:
        raise Exception('Incorrect signature')
    fn_name = match.group('fn_name')
    args = match.group('args')

    chars = string.digits + string.ascii_letters
    for suffix_len in range(10):
        for p in itertools.product(chars, repeat=suffix_len):
            fn_suffix = ''.join(p)
            test_signature = f'{fn_name}_{fn_suffix}{args}'
            sig_hash = Web3.sha3(text=test_signature).hex()[:10]
            if sig_hash.startswith(start_value):
                return test_signature, sig_hash
