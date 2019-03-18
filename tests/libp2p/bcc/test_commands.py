import pytest

from trinity.protocol.bcc_libp2p.commands import (
    Request,
    RequestMessage,
)

from trinity.protocol.bcc_libp2p.requests import (
    RequestRequest,
)


def test_request_codec():
    req_cmd = Request(cmd_id_offset=0, snappy_support=False)
    req_msg = RequestMessage(request_id=1, method_id=2)
    req_bytes = req_cmd.encode_payload(req_msg)
    req_msg_from_bytes = req_cmd.decode_payload(req_bytes)
    assert req_msg == req_msg_from_bytes


def test_request_request():
    pass
