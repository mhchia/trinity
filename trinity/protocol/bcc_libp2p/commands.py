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


class RequestBody(TypedDict):
    pass


class RequestMessage(TypedDict):
    request_id: int  # uint64
    method_id: int  # uint16
    # body: RequestBody


class Request(Command):
    _cmd_id = 0
    structure = [
        ('request_id', sedes.big_endian_int),
        ('method_id', sedes.big_endian_int),
    ]


class HelloRequestMessage(RequestBody):
    network_id: int  # uint8
    # latest_finalized_root: Hash32  # bytes32
    # latest_finalized_epoch: int  # uint64
    # best_root: Hash32  # bytes32
    # best_slot: int  # uint64


class ResponseBody(TypedDict):
    pass


class ResponseMessage(TypedDict):
    request_id: int
    # body: ResponseBody


# class Error(TypedDict):
#     code: int  # uint16
#     data: bytes  # bytes


# class ErrorResponseMessage(TypedDict):
#     request_id: int
#     error: Error


class Response(Command):
    _cmd_id = 0
    structure = [
        ('request_id', sedes.big_endian_int),
        ('method_id', sedes.big_endian_int),
    ]


# ResponseType = TypeVar('ResponseType', ResponseMessage, ErrorResponseMessage)
