from abc import (
    ABC,
)
import asyncio
import logging
from typing import (
    Awaitable,
    Callable,
    Dict,
    List,
    Type,
)

from mypy_extensions import (
    TypedDict,
)

from libp2p.connmgr import (
    BaseConnectionManager,
    DaemonConnectionManager,
)
from libp2p.dht import (
    BaseDHT,
    DaemonDHT,
)
from libp2p.host import (
    BaseHost,
    DaemonHost,
)
from libp2p.pubsub import (
    BasePubSub,
    DaemonPubSub,
)

from libp2p.p2pclient.datastructures import (
    PeerInfo,
    StreamInfo,
)
from libp2p.p2pclient.p2pclient import (
    ControlClient,
    ConnectionManagerClient,
    DHTClient,
    PubSubClient,
)
from libp2p.p2pclient.serialization import (
    read_unsigned_varint,
    write_unsigned_varint,
)

from p2p.protocol import (
    Command,
)

from trinity.protocol.bcc_libp2p.commands import (
    HelloRequest,
    HelloRequestMessage,
    HelloResponse,
    HelloResponseMessage,
    ErrorResponse,
)


logging.basicConfig(level=logging.DEBUG)


PROTOCO_ETH = "/eth/serenity"
PROTOCOL_RPC = f"{PROTOCO_ETH}/rpc/1.0.0"


class BaseNode(ABC):
    """
    Reference:
        - libp2p daemon: https://github.com/libp2p/go-libp2p-daemon/blob/master/daemon.go
        - sharding-p2p-poc: https://github.com/ethresearch/sharding-p2p-poc/blob/master/node.go
    """

    host: BaseHost
    dht: BaseDHT
    pubsub: BasePubSub
    connmgr: BaseConnectionManager


MethodHandler = Callable[
    [StreamInfo, asyncio.StreamReader, asyncio.StreamWriter],
    Awaitable[None],
]

METHOD_ID_HELLO = 0


class DaemonNode(BaseNode):
    _commands: List[Type[Command]] = [HelloRequest, HelloResponse, ErrorResponse]
    _method_handlers: Dict[int, MethodHandler]
    commands: List[Command]
    cmd_by_type: Dict[Type[Command], Command]
    logger = logging.getLogger('libp2p.bcc_libp2p.node.DaemonNode')
    network_id: int = 1

    def __init__(
            self,
            controlc: ControlClient,
            dhtc: DHTClient,
            pubsubc: PubSubClient,
            connmgrc: ConnectionManagerClient) -> None:
        self.host = DaemonHost(controlc)
        self.dht = DaemonDHT(dhtc)
        self.pubsub = DaemonPubSub(pubsubc)
        self.connmgr = DaemonConnectionManager(connmgrc)
        self._method_handlers = {
            METHOD_ID_HELLO: self._handler_hello,
        }
        self.commands = [
            cmd_class(cmd_id_offset=0, snappy_support=False)
            for cmd_class in self._commands
        ]
        self.cmd_by_type = {
            cmd_class: cmd_object
            for cmd_class, cmd_object in zip(self._commands, self.commands)
        }

    async def setup(self) -> None:
        await self.host.setup()
        await self.host.set_stream_handler(
            protocol_id=PROTOCOL_RPC,
            stream_handler=self._protocol_handler,
        )

    async def send_hello(self, peer_info: PeerInfo):
        """
        Send hello to the peer, exchange information, and disconnect if both are not compatible.
        FIXME: This is the workaround version. "Hello" should be done in the process of `connect`.
        Need to write:
            (
                `varint_method_id`,
                `varint_len_payload`,
                `payload`,
            )
        """
        # TODO: should check if we have the connections already
        await self.host.connect(peer_info)
        _, reader, writer = await self.host.new_stream(
            peer_id=peer_info.peer_id,
            protocol_ids=[PROTOCOL_RPC],
        )
        method_id = METHOD_ID_HELLO
        request_id = self._make_request_id()
        msg = HelloRequestMessage(
            request_id=request_id,
            method_id=method_id,
            network_id=self.network_id,
        )
        # write varint `method_id`
        write_unsigned_varint(writer, method_id)
        self._write_cmd_msg(msg, writer, HelloRequest)

        # read response
        msg_resp_hello = await self._read_cmd_msg(reader, HelloResponse)
        if msg_resp_hello["request_id"] != request_id:
            # NOTE: this should not happen, invalid response.
            await self.host.disconnect(peer_info.peer_id)
        if msg_resp_hello["network_id"] != self.network_id:
            # NOTE: different network, disconnect
            await self.host.disconnect(peer_info.peer_id)

        # hello succeeds

    async def _handler_hello(
            self,
            stream_info: StreamInfo,
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter) -> None:
        """
        Need to read:
            (
                `varint_len_payload`,
                `payload`,
            )
        """
        msg_dict_req_hello = await self._read_cmd_msg(reader, HelloRequest)
        msg_req_hello = HelloRequestMessage(**msg_dict_req_hello)
        # close the connection if the peer resides in different network
        if msg_req_hello["network_id"] != self.network_id:
            await self.host.disconnect(stream_info.peer_id)
            # TODO: write error message
            # self._write_cmd_msg(, writer, ErrorResponse)
        # check pass, write back the response
        msg_resp_hello = HelloResponseMessage(
            request_id=msg_req_hello["request_id"],
            network_id=self.network_id,
        )
        self._write_cmd_msg(msg_resp_hello, writer, HelloResponse)

    def _write_cmd_msg(
            self,
            msg: Dict,
            writer: asyncio.StreamWriter,
            cmd_type: Type[Command]) -> None:
        req_cmd_hello = self.cmd_by_type[cmd_type]
        req_bytes_hello = req_cmd_hello.encode_payload(msg)
        # write line of payload
        write_unsigned_varint(writer, len(req_bytes_hello))
        writer.write(req_bytes_hello)

    async def _read_cmd_msg(
            self,
            reader: asyncio.StreamReader,
            cmd_type: Type[Command]) -> Dict:
        len_payload = await read_unsigned_varint(reader)
        print(f"!@# _read_cmd_msg: len_payload={len_payload}")
        payload = await reader.read(len_payload)
        print(f"!@# _read_cmd_msg: payload={payload}")
        cmd = self.cmd_by_type[cmd_type]
        try:
            data = cmd.decode_payload(payload)
        except Exception:  # FIXME: catch exact exception
            cmd_error = self.cmd_by_type[ErrorResponse]
            data = cmd.decode_payload(payload)
        print(f"!@# _read_cmd_msg: data={data}")
        return data

    async def _protocol_handler(
            self,
            stream_info: StreamInfo,
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter) -> None:
        """
        Assume the peer has written:
            (
                `varint_method_id`,
                `varint_len_payload`,
                `payload`,
            )
        """
        method_id = await read_unsigned_varint(reader)
        if method_id not in self._method_handlers:
            # reject
            print("!@# rejected")
            pass
        print(f"!@# dispatched to method {method_id}")
        await self._method_handlers[method_id](
            stream_info=stream_info,
            reader=reader,
            writer=writer,
        )

    def _make_request_id(self) -> int:
        # FIXME: e.g. uuid int
        return 1
