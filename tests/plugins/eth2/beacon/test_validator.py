import asyncio
import logging
import time
from typing import (
    Tuple,
)

import pytest

from py_ecc import bls

from lahja import (
    BroadcastConfig,
)

from eth.exceptions import BlockNotFound

from trinity.config import BeaconChainConfig
from trinity.plugins.eth2.beacon.validator import (
    Validator,
)

from eth2.beacon._utils.hash import (
    hash_eth2,
)
from eth2.beacon.state_machines.forks.serenity.blocks import (
    SerenityBeaconBlock,
)
from eth2.beacon.state_machines.forks.serenity.configs import (
    SERENITY_CONFIG,
)
from eth2.beacon.state_machines.forks.xiao_long_bao.configs import (
    XIAO_LONG_BAO_CONFIG,
)
from eth2.beacon.tools.builder.initializer import (
    create_mock_genesis,
)
from eth2.beacon.tools.builder.proposer import (
    _get_proposer_index,
)
from trinity.plugins.eth2.beacon.slot_ticker import (
    NewSlotEvent,
)

from .helpers import (
    get_chain_db,
)


NUM_VALIDATORS = 8

privkeys = tuple(int.from_bytes(
    hash_eth2(str(i).encode('utf-8'))[:4], 'big')
    for i in range(NUM_VALIDATORS)
)
index_to_pubkey = {}
keymap = {}  # pub -> priv
for i, k in enumerate(privkeys):
    pubkey = bls.privtopub(k)
    index_to_pubkey[i] = pubkey
    keymap[pubkey] = k

genesis_time = int(time.time())

genesis_state, genesis_block = create_mock_genesis(
    num_validators=NUM_VALIDATORS,
    config=XIAO_LONG_BAO_CONFIG,
    # config=SERENITY_CONFIG,
    keymap=keymap,
    genesis_block_class=SerenityBeaconBlock,
    genesis_time=genesis_time,
)


class FakeProtocol:
    def __init__(self):
        self.inbox = []

    def send_new_block(self, block):
        self.inbox.append(block)


class FakePeer:
    def __init__(self):
        self.sub_proto = FakeProtocol()


class FakePeerPool:
    def __init__(self):
        self.connected_nodes = {}

    def add_peer(self, index):
        self.connected_nodes[index] = FakePeer()


def get_chain(db):
    beacon_chain_config = BeaconChainConfig('TestTestTest')
    chain_class = beacon_chain_config.beacon_chain_class
    return chain_class.from_genesis(
        base_db=db,
        genesis_state=genesis_state,
        genesis_block=genesis_block,
    )


async def get_validator(event_loop, event_bus, index) -> Validator:
    chain_db = await get_chain_db()
    chain = get_chain(chain_db.db)
    peer_pool = FakePeerPool()
    v = Validator(
        validator_index=index,
        chain=chain,
        peer_pool=peer_pool,
        privkey=keymap[index_to_pubkey[index]],
        event_bus=event_bus,
    )
    asyncio.ensure_future(v.run(), loop=event_loop)
    await v.events.started.wait()
    # yield to `validator._run`
    await asyncio.sleep(0)
    return v


async def get_linked_validators(event_loop, event_bus) -> Tuple[Validator, Validator]:
    alice_index = 0
    bob_index = 1
    alice = await get_validator(event_loop, event_bus, alice_index)
    bob = await get_validator(event_loop, event_bus, bob_index)
    alice.peer_pool.add_peer(bob_index)
    bob.peer_pool.add_peer(alice_index)
    return alice, bob


@pytest.mark.asyncio
async def test_validator_propose_block(caplog, event_loop, event_bus):
    caplog.set_level(logging.DEBUG)
    alice, bob = await get_linked_validators(event_loop=event_loop, event_bus=event_bus)

    head = alice.chain.get_canonical_head()
    state_machine = alice.chain.get_state_machine()
    state = state_machine.state
    block = alice.propose_block(
        slot=state.slot,  # FIXME: unsure which slot should be used here.
        state=state,
        state_machine=state_machine,
        head_block=head,
    )
    # test: ensure the proposed block is saved to the chaindb
    assert alice.chain.get_block_by_root(block.signed_root) == block

    # TODO: test: `canonical_head` should change after proposing?
    # new_head = alice.chain.get_canonical_head()
    # assert new_head != head

    # test: ensure the block is broadcast to bob
    assert block in alice.peer_pool.connected_nodes[bob.validator_index].sub_proto.inbox


@pytest.mark.asyncio
async def test_validator_skip_block(caplog, event_loop, event_bus):
    caplog.set_level(logging.DEBUG)
    alice = await get_validator(event_loop=event_loop, event_bus=event_bus, index=0)
    state_machine = alice.chain.get_state_machine()
    state = state_machine.state
    slot = state.slot + 1  # FIXME: unsure which slot should be used here.
    root_post_state = alice.skip_block(
        slot=slot,
        state=state,
        state_machine=state_machine,
    )
    with pytest.raises(BlockNotFound):
        alice.chain.get_canonical_block_by_slot(slot)
    assert state.root != root_post_state
    # TODO: more tests


@pytest.mark.asyncio
async def test_validator_new_slot(caplog, event_loop, event_bus, monkeypatch):
    caplog.set_level(logging.DEBUG)
    alice = await get_validator(event_loop=event_loop, event_bus=event_bus, index=0)
    state_machine = alice.chain.get_state_machine()
    state = state_machine.state
    new_slot = state.slot - 1  # FIXME: unsure which slot should be used here.
    index = _get_proposer_index(
        state,
        new_slot,
        state_machine.config,
    )

    is_proposing = True

    def propose_block(slot, state, state_machine, head_block):
        nonlocal is_proposing
        is_proposing = True

    def skip_block(slot, state, state_machine):
        nonlocal is_proposing
        is_proposing = False

    monkeypatch.setattr(alice, 'propose_block', propose_block)
    monkeypatch.setattr(alice, 'skip_block', skip_block)

    await alice.new_slot(new_slot)

    # test: either `propose_block` or `skip_block` should be called.
    assert is_proposing is not None
    if alice.validator_index == index:
        assert is_proposing
    else:
        assert not is_proposing


@pytest.mark.asyncio
async def test_validator_handle_new_slot(caplog, event_loop, event_bus, monkeypatch):
    alice = await get_validator(event_loop=event_loop, event_bus=event_bus, index=0)

    event_new_slot_called = asyncio.Event()

    async def new_slot(slot):
        event_new_slot_called.set()

    monkeypatch.setattr(alice, 'new_slot', new_slot)

    # sleep for `event_bus` ready
    await asyncio.sleep(0.01)

    event_bus.broadcast(
        NewSlotEvent(
            slot=1,
            elapsed_time=2,
        ),
        BroadcastConfig(internal=True),
    )
    await asyncio.wait_for(
        event_new_slot_called.wait(),
        timeout=2,
        loop=event_loop,
    )
