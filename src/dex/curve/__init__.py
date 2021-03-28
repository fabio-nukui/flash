from .client import CurveProtocol, CurveClient, CurvePool


EllipsisClient: CurveClient = CurveProtocol(
    class_name='EllipsisClient',
    dex_name='ellipsis',
    chain_id=56,
    swap_fee=4
)

__all__ = [
    'CurvePool',
    'EllipsisClient',
]
