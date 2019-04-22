import asyncio
from pathlib import Path
import uuid
import time
from typing import (
    cast,
)

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

from eth.db.atomic import (
    AtomicDB,
)

from eth2.beacon.db.chain import (
    BeaconChainDB,
)
from eth2.beacon._utils.hash import (
    hash_eth2,
)
from eth2.beacon.state_machines.forks.serenity.blocks import (
    SerenityBeaconBlock,
)
from eth2.beacon.state_machines.forks.xiao_long_bao.configs import (
    XIAO_LONG_BAO_CONFIG,
)
from eth2.beacon.tools.builder.initializer import (
    create_mock_genesis,
)

from trinity.constants import (
    NETWORKING_EVENTBUS_ENDPOINT,
)
from trinity.endpoint import (
    TrinityEventBusEndpoint,
)

from .helpers import (
    get_directly_linked_peers_in_peer_pools,
    get_chain_db,
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

genesis_state, genesis_block = create_mock_genesis(
    num_validators=NUM_VALIDATORS,
    config=XIAO_LONG_BAO_CONFIG,
    keymap=keymap,
    genesis_block_class=SerenityBeaconBlock,
    genesis_time=int(time.time()),
)


# config = XIAO_LONG_BAO_CONFIG

# # Only used for testing
# num_validators = 10
# privkeys = tuple(2 ** i for i in range(num_validators))
# keymap = {}
# for k in privkeys:
#     keymap[bls.privtopub(k)] = k
# state, block = create_mock_genesis(
#     num_validators=num_validators,
#     config=config,
#     keymap=keymap,
#     genesis_block_class=SerenityBeaconBlock,
#     genesis_time=ZERO_TIMESTAMP,
# )
# return cast('BeaconChain', self.beacon_chain_class.from_genesis(
#     base_db=base_db,
#     genesis_state=state,
#     genesis_block=block,
# ))

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


def get_chain(db):
    beacon_chain_config = BeaconChainConfig('TestTestTest')
    chain_class = beacon_chain_config.beacon_chain_class
    return chain_class.from_genesis(
        base_db=db,
        genesis_state=genesis_state,
        genesis_block=genesis_block,
    )


async def get_linked_validators(request, event_loop):
    alice_chain_db = await get_chain_db()
    alice_chain = get_chain(alice_chain_db.db)
    alice_index = 0
    bob_chain_db = await get_chain_db()
    bob_chain = get_chain(bob_chain_db.db)
    bob_index = 1
    # bob_chain_db = BeaconChainDB(AtomicDB())
    alice, alice_peer_pool, bob, bob_peer_pool = await get_directly_linked_peers_in_peer_pools(
        request,
        event_loop,
        alice_chain_db=alice_chain_db,
        bob_chain_db=bob_chain_db,
    )
    alice_validator = Validator(
        validator_index=alice_index,
        chain=alice_chain,
        peer_pool=alice_peer_pool,
        privkey=keymap[index_to_pubkey[alice_index]],
        event_bus=await get_event_bus(event_loop),
    )
    bob_validator = Validator(
        validator_index=bob_index,
        chain=bob_chain,
        peer_pool=bob_peer_pool,
        privkey=keymap[index_to_pubkey[bob_index]],
        event_bus=await get_event_bus(event_loop),
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
