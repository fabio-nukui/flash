import math
from typing import Union

from core import Token, TokenAmount


def decompose_amount(amount: Union[int, TokenAmount]) -> tuple[int, int, int]:
    """Decompose amount into 6 bits exponent and 14 bits mantissa. Can represent numbers up to
    2 ** 83 wei = 9.67M BNB, with good precision at amounts over 2 ** 20

    Args:
        amount (int): Amount to be decomposed, must be in interval [2 ** 20, 2 ** 83)

    Returns:
        tuple[int, int, int]: tuple of (aproximated amount, exponent, mantissa)
    """
    assert 2 ** 20 <= amount < 2 ** 83, \
        f'amount_last must be between [2 ** 20, 2 ** 83), received {amount=}'
    amount = amount.amount if isinstance(amount, TokenAmount) else amount
    exp = math.ceil(math.log2(amount)) - 20
    mant = math.ceil(amount / 2 ** (exp + 6)) - 1
    assert 0 <= exp < 64, exp  # fail-safe to avoid overflow errors
    assert 0 < mant < 2 ** 14, mant  # fail-safe to avoid overflow errors

    return mant << exp + 6, exp, mant


def encode_data32(dex_0: int, dex_1: int, exp: int, mant: int, token: Union[str, Token]) -> bytes:
    """Encode data in format:
    {uint6 dex_0}{uint6 dex_1}{uint6 amount_exp}{uint14 amount_mant}{bytes20 token}
    """
    assert 0 <= dex_0 < 64, f'dex_0 must be between [0, 64), received {dex_0=}'
    assert 0 <= dex_1 < 64, f'dex_1 must be between [0, 64), received {dex_1=}'
    assert dex_0 != dex_1, 'dex_0 and dex_1 must be different'
    token = token.address if isinstance(token, Token) else token
    data = (
        (dex_0 << 250)
        + (dex_1 << 244)
        + (exp << 238)
        + (mant << 224)
        + (int(token, 0) << 64)
    )
    return data.to_bytes(32, 'big')


def encode_data64(
    dex_0: int,
    dex_1: int,
    exp: int,
    mant: int,
    path: list[Union[str, Token]],
) -> tuple[bytes, bytes]:
    """Encode data in format:
    {uint6 dex_0}{uint6 dex_1}{uint6 amount_exp}{uint14 amount_mant}{bytes20 token0}{bytes20 token1}{bytes20 token2}  # noqa: E501
    (data is split in two 32 bytes chunks)
    """
    assert 0 <= dex_0 < 64, f'dex_0 must be between [0, 64), received {dex_0=}'
    assert 0 <= dex_1 < 64, f'dex_1 must be between [0, 64), received {dex_1=}'
    assert dex_0 != dex_1, 'dex_0 and dex_1 must be different'
    assert len(path) in (2, 3)
    path = [
        token.address if isinstance(token, Token) else token
        for token in path
    ]
    data0 = (
        (dex_0 << 250)
        + (dex_1 << 244)
        + (exp << 238)
        + (mant << 224)
        + (int(path[0], 0) << 64)
        + int(path[1][:18], 0)
    )
    data1 = (
        (int('0x' + path[1][18:], 0) << 160)
        + (int(path[2], 0) if len(path) == 3 else 0)
    )
    return data0.to_bytes(32, 'big'), data1.to_bytes(32, 'big')
