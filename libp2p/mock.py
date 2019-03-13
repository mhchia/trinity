import asyncio
from collections import (
    defaultdict,
)
import functools
from typing import (
    Dict,
    MutableSet,
    Tuple,
)
import uuid

from eth_keys import keys

from multiaddr import Multiaddr

import multihash

from libp2p.p2pclient.datastructures import (
    PeerID,
    PeerInfo,
    StreamInfo,
)
from libp2p.p2pclient.exceptions import (
    ControlFailure,
)
from libp2p.p2pclient.p2pclient import (
    read_pbmsg_safe,
    write_pbmsg,
)
from libp2p.p2pclient.pb import p2pd_pb2 as p2pd_pb
from libp2p.p2pclient.pb import crypto_pb2 as crypto_pb


class MockStreamReaderWriter:
    _buf: bytes

    def __init__(self):
        self._buf = b""

    def write(self, data):
        self._buf = self._buf + data

    async def read(self, n=-1):
        if n == 0:
            raise ValueError
        if n == -1:
            n = len(self._buf)
        # NOTE: polling the buffer, to simulate `asyncio.StreamReader.read`
        while len(self._buf) == 0:
            await asyncio.sleep(0.01)
        data = self._buf[:n]
        self._buf = self._buf[n:]
        return data

    async def readexactly(self, n):
        data = await self.read(n)
        if len(data) != n:
            raise asyncio.IncompleteReadError(partial=data, expected=n)
        return data

    async def drain(self):
        # do nothing
        pass

    def close(self):
        pass


class MockControlClient:

    _map_peer_id_to_control_client = None
    _uuid = None
    _peer_id = None
    _maddrs = None
    _peers = None

    handlers = None
    control_maddr = None
    listen_maddr = None

    def __init__(self, map_peer_id_to_control_client):
        """
        Args:
            map_peer_id_to_control_client (dict): The mutable mapping from
                `peer_id_to_immutable(peer_id)` to its corresponding `MockControlClient` object.
        """
        self._uuid = uuid.uuid1()
        self._privkey = keys.PrivateKey(self._uuid.bytes.ljust(32, b'\x00'))
        peer_id_bytes = multihash.digest(
            self._privkey.public_key.to_bytes(),
            multihash.Func.sha2_256,
        ).encode()
        self._peer_id = PeerID(peer_id_bytes)
        self._maddrs = [Multiaddr(f"/unix/maddr_{self._uuid}")]

        self._peers = set()
        self._map_peer_id_to_control_client = map_peer_id_to_control_client
        self._map_peer_id_to_control_client[self._peer_id] = self

        self.control_maddr = f"/unix/control_{self._uuid}"
        self.listen_maddr = f"/unix/listen__{self._uuid}"
        self.handlers = {}

    def __del__(self):
        del self._map_peer_id_to_control_client[self._peer_id]

    async def _dispatcher(self, reader, writer):
        pb_stream_info = p2pd_pb.StreamInfo()
        await read_pbmsg_safe(reader, pb_stream_info)
        stream_info = StreamInfo.from_pb(pb_stream_info)
        try:
            handler = self.handlers[stream_info.proto]
        except KeyError:
            # simulate that the daemon has rejected the stream for us,
            # so we shouldn't be called here.
            return
        await handler(stream_info, reader, writer)

    async def listen(self):
        pass

    async def close(self):
        self._map_peer_id_to_control_client.remove(self._peer_id)

    async def identify(self):
        return self._peer_id, self._maddrs

    async def connect(self, peer_id, maddrs):
        if peer_id not in self._map_peer_id_to_control_client:
            raise ControlFailure
        peer_client = self._map_peer_id_to_control_client[peer_id]
        if len(maddrs) == 0:
            raise ControlFailure
        correct_maddrs = peer_client._maddrs
        is_found = all([target_maddr in correct_maddrs for target_maddr in maddrs])
        if not is_found:
            raise ControlFailure
        self._peers.add(peer_id)
        peer_client._peers.add(self._peer_id)

    async def list_peers(self):
        return tuple(
            PeerInfo(
                peer_id,
                self._map_peer_id_to_control_client[peer_id]._maddrs,
            )
            for peer_id in self._peers
        )

    async def disconnect(self, peer_id):
        if peer_id not in self._map_peer_id_to_control_client:
            return
        peer = self._map_peer_id_to_control_client[peer_id]
        self._peers.remove(peer_id)
        peer._peers.remove(self._peer_id)

    async def stream_open(self, peer_id, protocols):
        if len(protocols) == 0:
            raise ControlFailure(f'len(protocols) should not be 0, protocols={protocols}')

        protocol_chosen = protocols[0]

        reader = MockStreamReaderWriter()
        writer = MockStreamReaderWriter()

        stream_info_pb = StreamInfo(
            peer_id=self._peer_id,
            addr=self._maddrs[0],
            proto=protocol_chosen,
        ).to_pb()
        await write_pbmsg(writer, stream_info_pb)

        if peer_id not in self._map_peer_id_to_control_client:
            raise ControlFailure(f"failed to find the peer {peer_id}")
        peer_control_client = self._map_peer_id_to_control_client[peer_id]

        # pre-check the handler map of our target peer.
        # if the peer hasn't registered a handler for the protocol, daemon returns error to us,
        # and then the p2pclient should raise `ControlFailure`
        if protocol_chosen not in peer_control_client.handlers:
            raise ControlFailure(
                f"the target peer doesn't register the protocol `{protocol_chosen}`"
            )

        # schedule `_dispatcher` of the target peer
        # your reader is its writer, vice versa.
        asyncio.ensure_future(
            peer_control_client._dispatcher(reader=writer, writer=reader)
        )

        stream_info_peer = StreamInfo(
            peer_id=peer_id,
            addr=peer_control_client._maddrs[0],  # chose the first one at my will
            proto=protocol_chosen,
        )
        return stream_info_peer, reader, writer

    async def stream_handler(self, proto, handler_cb):
        self.handlers[proto] = handler_cb

    def _bfs(self, peer_filter) -> Tuple[PeerID, ...]:
        visited_topic_nodes = set()
        queue = []
        queue.append(self._peer_id)
        while len(queue) != 0:
            current_peer_id = queue.pop(0)
            visited_topic_nodes.add(current_peer_id)
            peer_controlc = self._map_peer_id_to_control_client[current_peer_id]
            unvisited_peers = tuple(
                peer_id
                for peer_id in peer_controlc._peers
                if peer_id not in visited_topic_nodes
            )
            queue.extend(filter(peer_filter, unvisited_peers))
        return tuple(visited_topic_nodes)


class MockPubSubClient:
    _topic_subscribed_streams: Dict[str, Tuple[MockStreamReaderWriter, MockStreamReaderWriter]]
    _control_client: MockControlClient
    _map_peer_id_to_pubsub_client: Dict[PeerID, 'MockPubSubClient']

    def __init__(
            self,
            control_client: MockControlClient,
            map_peer_id_to_pubsub_client: Dict[PeerID, 'MockPubSubClient']):
        self._topic_subscribed_streams = {}
        self._control_client = control_client
        self._map_peer_id_to_pubsub_client = map_peer_id_to_pubsub_client
        self._map_peer_id_to_pubsub_client[self._control_client._peer_id] = self

    def __del__(self):
        del self._map_peer_id_to_pubsub_client[self.peer_id]

    @property
    def peer_id(self) -> PeerID:
        return self._control_client._peer_id

    @property
    def topics(self) -> Tuple[str, ...]:
        return tuple(self._topic_subscribed_streams.keys())

    async def get_topics(self) -> Tuple[str, ...]:
        return self.topics

    async def list_peers(self, topic: str) -> Tuple[PeerID, ...]:
        pinfos = await self._control_client.list_peers()
        peers_control = tuple(
            pinfo.peer_id
            for pinfo in pinfos
        )
        return tuple(
            peer_id
            for peer_id in peers_control
            if topic in self._map_peer_id_to_pubsub_client[peer_id].topics
        )

    async def publish(self, topic: str, data: bytes) -> None:
        nodes_to_publish = self._do_bfs(topic)
        for peer_id in nodes_to_publish:
            pubsubc = self._map_peer_id_to_pubsub_client[peer_id]
            stream_pair = pubsubc._topic_subscribed_streams[topic]
            ps_msg = p2pd_pb.PSMessage(
                data=data,
                topicIDs=[topic],
            )
            # TODO: the setter of `PSMessage.from_field` doesn't work, workaround with `setattr`
            setattr(ps_msg, 'from', self.peer_id.to_bytes())
            await write_pbmsg(stream_pair[0], ps_msg)

    def _pubsub_peer_filter(self, peer_id: PeerID, topic: str) -> bool:
        # check if the peer runs pubsub
        if peer_id not in self._map_peer_id_to_pubsub_client:
            return False
        peer_pubsubc = self._map_peer_id_to_pubsub_client[peer_id]
        # go through the peer only if it subscribes to the topic
        if topic not in peer_pubsubc.topics:
            return False
        return True

    def _do_bfs(self, topic: str) -> Tuple[PeerID, ...]:
        peer_filter = functools.partial(self._pubsub_peer_filter, topic=topic)
        return self._control_client._bfs(peer_filter)

    def _unsubscribe(self, topic: str) -> None:
        del self._topic_subscribed_streams[topic]

    async def subscribe(self, topic: str) -> Tuple[MockStreamReaderWriter, MockStreamReaderWriter]:
        if topic in self.topics:
            return
        reader = MockStreamReaderWriter()
        writer = MockStreamReaderWriter()
        setattr(writer, 'close', functools.partial(self._unsubscribe, topic=topic))
        stream_pair = (reader, writer)
        self._topic_subscribed_streams[topic] = stream_pair
        return stream_pair


class MockDHTClient:

    KVALUE = 20

    _control_client: MockControlClient
    _provides_store = MutableSet[bytes]
    _values_store: Dict[bytes, bytes]
    _map_peer_id_to_dht_client: Dict[PeerID, 'MockDHTClient']

    def __init__(
            self,
            control_client: MockControlClient,
            map_peer_id_to_dht_client: Dict[PeerID, 'MockDHTClient']) -> None:
        self._control_client = control_client
        self._provides_store = set()
        self._values_store = {}
        key_for_pubkey = self._make_key_for_peer_id(self.peer_id)
        self._values_store[key_for_pubkey] = self._control_client._privkey.public_key.to_bytes()
        self._map_peer_id_to_dht_client = map_peer_id_to_dht_client
        self._map_peer_id_to_dht_client[self._control_client._peer_id] = self

    @property
    def peer_id(self) -> PeerID:
        return self._control_client._peer_id

    @property
    def reachable_nodes(self) -> Tuple[PeerID, ...]:

        def _dht_peer_filter(peer_id: PeerID) -> bool:
            # only go through the nodes who run dht
            # return peer_id in self._map_peer_id_to_dht_client
            return True
        return self._control_client._bfs(_dht_peer_filter)

    async def find_peer(self, peer_id: PeerID) -> PeerInfo:
        if peer_id not in self._control_client._map_peer_id_to_control_client:
            raise ControlFailure(f"peer {peer_id} does not exist")
        if peer_id not in self.reachable_nodes:
            raise ControlFailure(f"no route to peer {peer_id}")
        peer_controlc = self._control_client._map_peer_id_to_control_client[peer_id]
        return PeerInfo(
            peer_id=peer_controlc._peer_id,
            addrs=peer_controlc._maddrs,
        )

    async def find_peers_connected_to_peer(self, peer_id: PeerID) -> Tuple[PeerInfo, ...]:
        if peer_id not in self._control_client._map_peer_id_to_control_client:
            return tuple()
        peer_controlc = self._control_client._map_peer_id_to_control_client[peer_id]
        pinfos = tuple(
            PeerInfo(
                peer_id_neighbor,
                self._control_client._map_peer_id_to_control_client[peer_id_neighbor]._maddrs,
            )
            for peer_id_neighbor in peer_controlc._peers
        )
        return pinfos

    async def find_providers(self, content_id_bytes: bytes, count: int) -> Tuple[PeerInfo, ...]:
        pinfos = tuple(
            PeerInfo(
                peer_id,
                self._control_client._map_peer_id_to_control_client[peer_id]._maddrs,
            )
            for peer_id in self.reachable_nodes
            if content_id_bytes in self._map_peer_id_to_dht_client[peer_id]._provides_store
        )
        return pinfos[:count]

    async def provide(self, cid: bytes) -> None:
        # ignore `ProvRecord`
        self._provides_store.add(cid)

    async def get_closest_peers(self, key: bytes) -> Tuple[PeerID, ...]:
        peers_sorted = sorted(
            self.reachable_nodes,
            key=lambda x: self._distance(x.to_bytes(), key),
        )
        return tuple(peers_sorted)[:self.KVALUE]

    @staticmethod
    def _make_key_for_peer_id(peer_id: PeerID) -> bytes:
        return b"/pk/" + peer_id.to_bytes()

    async def get_public_key(self, peer_id: PeerID) -> crypto_pb.PublicKey:
        key = self._make_key_for_peer_id(peer_id)
        closest_peers = await self.get_closest_peers(key)
        for peer_id in closest_peers:
            peer_dhtc = self._map_peer_id_to_dht_client[peer_id]
            if key in peer_dhtc._values_store:
                return crypto_pb.PublicKey(
                    Type=crypto_pb.Secp256k1,
                    Data=peer_dhtc._values_store[key],
                )
        raise ControlFailure(f"public key of peer {peer_id} is not found")

    async def get_value(self, key: bytes) -> bytes:
        matched_values = await self.search_value(key)
        if len(matched_values) == 0:
            raise ControlFailure(f"key={key} is not found")
        return matched_values[0]

    async def search_value(self, key: bytes) -> Tuple[bytes, ...]:
        values = set()
        closest_peers = await self.get_closest_peers(key)
        for peer_id in closest_peers:
            peer_dhtc = self._map_peer_id_to_dht_client[peer_id]
            if key in peer_dhtc._values_store:
                values.add(peer_dhtc._values_store[key])
        # there is a way to select the best value, but here we just sort it by value
        return tuple(sorted(values))

    async def put_value(self, key: bytes, value: bytes) -> None:
        closet_peers = await self.get_closest_peers(key)
        for peer_id in closet_peers:
            self._map_peer_id_to_dht_client[peer_id]._values_store[key] = value

    @staticmethod
    def _distance(bytes_0: bytes, bytes_1: bytes) -> int:
        int_0 = int.from_bytes(bytes_0, 'big')
        int_1 = int.from_bytes(bytes_1, 'big')
        return int_0 ^ int_1


class MockConnectionManagerClient:
    _control_client: MockControlClient
    _map_peer_tag_weight: Dict[PeerID, Dict[str, int]]
    _low_water_mark: int
    _high_water_mark: int

    def __init__(
            self,
            control_client: MockControlClient,
            low_water_mark: int,
            high_water_mark: int) -> None:
        self._control_client = control_client
        self._map_peer_tag_weight = defaultdict(lambda: defaultdict(dict))
        self._low_water_mark = low_water_mark
        self._high_water_mark = high_water_mark

    async def tag_peer(self, peer_id: PeerID, tag: str, weight: int) -> None:
        self._map_peer_tag_weight[peer_id][tag] = weight

    async def untag_peer(self, peer_id: PeerID, tag: str) -> None:
        if peer_id in self._map_peer_tag_weight and tag in self._map_peer_tag_weight[peer_id]:
            del self._map_peer_tag_weight[peer_id][tag]

    def _count_weight(self, peer_id: PeerID) -> int:
        value = 0
        for map_tag_weight in self._map_peer_tag_weight.values():
            value += sum(map_tag_weight.values())
        return value

    # NOTE: leave the "autotrim" undone here, which needs `notify` feature in `ControlClient`
    async def trim(self) -> None:
        peers = self._control_client._peers
        peers_sorted = sorted(peers, key=self._count_weight)
        peers_to_trim = peers_sorted[:-self._low_water_mark]
        for peer_id in peers_to_trim:
            await self._control_client.disconnect(peer_id)
