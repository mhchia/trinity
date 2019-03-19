"""
Based on https://github.com/ethereum/eth2.0-specs/blob/863f85c45ab2e3327c8c2e5f620af040b239fb40/specs/networking/rpc-interface.md  # noqa: E501
"""

import asyncio
from typing import (
    Awaitable,
    Callable,
    TypeVar,
)

from eth_typing import (
    Hash32,
)

from mypy_extensions import (
    TypedDict,
)

from rlp import sedes

from eth2.beacon.typing import (
    Slot,
)

from libp2p.p2pclient.datastructures import (
    StreamInfo,
)

from p2p.protocol import (
    Command,
)


MethodRequestHandler = Callable[
    [StreamInfo, int, asyncio.StreamReader, asyncio.StreamWriter],
    Awaitable[None],
]


class HelloRequest(Command):
    _cmd_id = 0
    structure = [
        ('request_id', sedes.big_endian_int),
        ('method_id', sedes.big_endian_int),
        ('network_id', sedes.big_endian_int),
    ]


class HelloRequestMessage(TypedDict):
    request_id: int  # uint64
    method_id: int  # uint16

    # ## body ###
    network_id: int  # uint8
    # latest_finalized_root: Hash32  # bytes32
    # latest_finalized_epoch: int  # uint64
    # best_root: Hash32  # bytes32
    # best_slot: int  # uint64


class HelloResponse(Command):
    _cmd_id = 1
    structure = [
        ('request_id', sedes.big_endian_int),
        ('network_id', sedes.big_endian_int),
    ]


class HelloResponseMessage(TypedDict):
    request_id: int

    # ## body ###
    network_id: int  # uint8
    # latest_finalized_root: Hash32  # bytes32
    # latest_finalized_epoch: int  # uint64
    # best_root: Hash32  # bytes32
    # best_slot: int  # uint64


class ErrorResponseMessage(TypedDict):
    request_id: int
    code: int  # uint16
    data: bytes  # bytes


class ErrorResponse(Command):
    _cmd_id = 2
    structure = [
        ('request_id', sedes.big_endian_int),
        ('code', sedes.big_endian_int),
        ('data', sedes.binary),
    ]


# ResponseType = TypeVar('ResponseType', ResponseMessage, ErrorResponseMessage)
