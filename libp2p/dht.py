from abc import (
    ABC,
    abstractmethod,
)

from typing import (
    Tuple,
)

from .p2pclient.datastructures import (
    PeerID,
    PeerInfo,
)
from .p2pclient.pb import (
    crypto_pb,
)


class BaseDHT(ABC):
    """
    Reference:
        - go-libp2p-kad-dht: https://github.com/libp2p/go-libp2p-kad-dht
        - libp2p daemon bindings: p2pclient/p2pclient.py
    """
    @abstractmethod
    async def find_peer(self, peer_id: PeerID) -> PeerInfo:
        pass

    @abstractmethod
    async def find_peers_connected_to_peer(self, peer_id: PeerID) -> Tuple[PeerInfo, ...]:
        pass

    @abstractmethod
    async def find_providers(self, content_id_bytes: bytes, count: int) -> Tuple[PeerInfo, ...]:
        pass

    @abstractmethod
    async def get_closest_peers(self, key: bytes) -> Tuple[PeerID, ...]:
        pass

    @abstractmethod
    async def get_public_key(self, peer_id: PeerID) -> crypto_pb.PublicKey:
        pass

    @abstractmethod
    async def get_value(self, key: bytes) -> bytes:
        pass

    @abstractmethod
    async def search_value(self, key: bytes) -> Tuple[bytes, ...]:
        pass

    @abstractmethod
    async def put_value(self, key: bytes, value: bytes) -> None:
        pass

    @abstractmethod
    async def provide(self, cid: bytes) -> None:
        pass
