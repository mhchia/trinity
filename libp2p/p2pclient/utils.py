from typing import (
    Any,
)

from .exceptions import ControlFailure
from .pb import p2pd_pb2 as p2pd_pb


# TODO: pb typing
def raise_if_failed(response: Any) -> None:
    if response.type == p2pd_pb.Response.ERROR:  # type: ignore
        raise ControlFailure(
            f"connect failed. msg={response.error.msg}"
        )