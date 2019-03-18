from abc import (
    ABC,
)
import asyncio

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

from .methods import (
    MethodRequestHandler,
)


PROTOCO_ETH = "/eth/serenity"
PROTOCOL_RPC = f"{PROTOCO_ETH}/rpc/1.0.0"


class Request(TypedDict):
    pass


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


class DaemonNode(BaseNode):
    method_handlers: []

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

    async def _protocol_handler(
            self,
            stream_info: StreamInfo,
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter) -> None:
        pass

    async def setup(self):
        await self.host.setup()
        await self.host.set_stream_handler(
            protocol_id=PROTOCOL_RPC,
            stream_handler=self._protocol_handler,
        )
        pass
