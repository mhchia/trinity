from trinity.protocol.bcc_libp2p.commands import (
    HelloRequest,
    HelloRequestMessage,
)

# from trinity.protocol.bcc_libp2p.requests import (
#     HelloRequest,
# )


def test_hello_request_codec():
    req_cmd_hello = HelloRequest(cmd_id_offset=0, snappy_support=False)
    req_msg_hello = HelloRequestMessage(request_id=1, method_id=2, network_id=3)
    req_bytes_hello = req_cmd_hello.encode_payload(req_msg_hello)
    req_msg_from_bytes_hello = req_cmd_hello.decode_payload(req_bytes_hello)
    assert req_msg_hello == req_msg_from_bytes_hello


def test_request_request():
    pass
