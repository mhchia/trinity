from p2p.protocol import (
    BaseRequest,
)

from trinity.protocol.bcc_libp2p.commands import (
    Request,
    RequestMessage,
    Response,
)


class HelloRequest(BaseRequest[RequestMessage]):
    cmd_type = Response
    response_type = Response

    def __init__(self, request_id: int, method_id: int) -> None:
        self.command_payload = RequestMessage(
            request_id=request_id,
            method_id=method_id,
        )
