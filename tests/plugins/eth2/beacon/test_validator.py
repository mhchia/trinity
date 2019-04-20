import asyncio
from pathlib import Path
import uuid

import pytest

from py_ecc import bls

from lahja import (
    ConnectionConfig,
)

from eth.db.atomic import AtomicDB

from eth2.beacon.db.chain import BeaconChainDB
from trinity.db.beacon.chain import BaseAsyncBeaconChainDB

from trinity.config import BeaconChainConfig
from trinity.plugins.eth2.beacon.validator import (
    Validator,
)

from eth2.beacon._utils.hash import (
    hash_eth2,
)

from trinity.constants import (
    NETWORKING_EVENTBUS_ENDPOINT,
)
from trinity.endpoint import (
    TrinityEventBusEndpoint,
)

from .helpers import (
    get_directly_linked_peers_in_peer_pools,
    get_genesis_chain_db,
)


NUM_VALIDATORS = 2

privkeys = tuple(int.from_bytes(
    hash_eth2(str(i).encode('utf-8'))[:4], 'big')
    for i in range(NUM_VALIDATORS)
)
index_to_pubkey = {}
keymap = {}  # pub -> priv
for i, k in enumerate(privkeys):
    index_to_pubkey[i] = bls.privtopub(k)
    keymap[bls.privtopub(k)] = k

pubkeys = list(keymap)


# class FakePeer:
#     def __init__(self):
#         pass

#     def sub_proto(self):
#         pass


# class FakeProtocol:
#     def send_new_block(self, block):
#         pass


# class FakePeerPool:
#     def __init__(self):
#         self._connected_nodes = {}

#     @property
#     def connected_nodes(self):
#         return self._connected_nodes


async def get_event_bus(event_loop):
    endpoint = TrinityEventBusEndpoint()
    # Tests run concurrently, therefore we need unique IPC paths
    ipc_path = Path(f"networking-{uuid.uuid4()}.ipc")
    networking_connection_config = ConnectionConfig(
        name=NETWORKING_EVENTBUS_ENDPOINT,
        path=ipc_path
    )
    await endpoint.start_serving(networking_connection_config, event_loop)
    await endpoint.connect_to_endpoints(networking_connection_config)
    return endpoint


async def get_validator(request, event_loop, index, peer_pool=None, db=None) -> Validator:
    beacon_chain_config = BeaconChainConfig('TestTestTest')
    chain_class = beacon_chain_config.beacon_chain_class
    chain = chain_class(db)
    return Validator(
        validator_index=index,
        chain=chain,
        peer_pool=peer_pool,
        privkey=keymap[index_to_pubkey[index]],
        event_bus=await get_event_bus(event_loop),
    )


async def get_linked_validators(request, event_loop):
    alice_chain_db = await get_genesis_chain_db()
    bob_chain_db = await get_genesis_chain_db()
    alice, alice_peer_pool, bob, bob_peer_pool = await get_directly_linked_peers_in_peer_pools(
        request,
        event_loop,
        alice_chain_db=alice_chain_db,
        bob_chain_db=bob_chain_db,
    )
    alice_validator = await get_validator(
        request=request,
        event_loop=event_loop,
        index=0,
        peer_pool=alice_peer_pool,
        db=alice_chain_db.db,
    )
    bob_validator = await get_validator(
        request=request,
        event_loop=event_loop,
        index=1,
        peer_pool=bob_peer_pool,
        db=bob_chain_db.db,
    )
    return alice_validator, bob_validator


@pytest.mark.asyncio
async def test_validator_run(request, event_loop):
    alice_validator, bob_validator = await get_linked_validators(request, event_loop)
    asyncio.ensure_future(alice_validator.run(), loop=event_loop)
    asyncio.ensure_future(bob_validator.run(), loop=event_loop)

    await alice_validator.events.started.wait()
    await bob_validator.events.started.wait()


@pytest.mark.asyncio
async def test_validator_propose_block(request, event_loop):
    alice_validator, bob_validator = await get_linked_validators(request, event_loop)
    asyncio.ensure_future(alice_validator.run(), loop=event_loop)
    asyncio.ensure_future(bob_validator.run(), loop=event_loop)

    await alice_validator.events.started.wait()
    await bob_validator.events.started.wait()

    head = alice_validator.chain.get_canonical_head()
    print(f"!@# head={head.slot}")
    state_machine = alice_validator.chain.get_state_machine(at_block=head)
    state = state_machine.state
    alice_validator.propose_block(
        slot=0,
        state=state,
        state_machine=state_machine,
        head_block=head,
    )
