import logging

from cancel_token import (
    CancelToken,
)

from eth_keys.datatypes import PrivateKey

from eth2.beacon.chains.base import BeaconChain
from eth2.beacon.state_machines.forks.serenity.blocks import (
    SerenityBeaconBlock,
)
from eth2.beacon.state_machines.base import BaseBeaconStateMachine  # noqa: F401
from eth2.beacon.tools.builder.proposer import (
    _get_proposer_index,
    create_block_on_state,
)
from eth2.beacon.types.blocks import BaseBeaconBlock
from eth2.beacon.types.states import BeaconState

from trinity.endpoint import TrinityEventBusEndpoint
from trinity.protocol.bcc.peer import BCCPeerPool
from trinity.plugins.eth2.beacon.slot_ticker import (
    NewSlotEvent,
)
from trinity._utils.shellart import (
    bold_green,
    bold_red,
)

from p2p.service import BaseService


class Validator(BaseService):
    """
    Reference: https://github.com/ethereum/trinity/blob/master/eth2/beacon/tools/builder/proposer.py#L175  # noqa: E501
    """

    validator_index: int
    chain: BeaconChain
    peer_pool: BCCPeerPool
    privkey: PrivateKey
    event_bus: TrinityEventBusEndpoint

    logger = logging.getLogger('trinity.plugins.eth2.beacon.Validator')

    def __init__(
            self,
            validator_index: int,
            chain: BeaconChain,
            peer_pool: BCCPeerPool,
            privkey: PrivateKey,
            event_bus: TrinityEventBusEndpoint,
            token: CancelToken = None) -> None:
        super().__init__(token)
        self.validator_index = validator_index
        self.chain = chain
        self.peer_pool = peer_pool
        self.privkey = privkey
        self.event_bus = event_bus

    async def _run(self) -> None:
        await self.event_bus.wait_until_serving()
        self.logger.debug(bold_green("validator running!!!"))
        self.run_daemon_task(self.handle_new_slot())
        await self.cancellation()

    async def handle_new_slot(self) -> None:
        """
        The callback for `SlotTicker`, to be called whenever new slot is ticked.
        """
        async for event in self.event_bus.stream(NewSlotEvent):
            await self.new_slot(event.slot)

    async def new_slot(self, slot: int) -> None:
        head = self.chain.get_canonical_head()
        state_machine = self.chain.get_state_machine()
        state = state_machine.state
        self.logger.debug(
            bold_green(f"head: slot={head.slot}, state root={head.state_root}")
        )
        proposer_index = _get_proposer_index(
            state_machine,
            state,
            slot,
            head.root,
            state_machine.config,
        )
        if self.validator_index == proposer_index:
            self.propose_block(
                slot=slot,
                state=state,
                state_machine=state_machine,
                head_block=head,
            )
        else:
            self.skip_block(
                slot=slot,
                state=state,
                state_machine=state_machine,
                parent_block=head,
            )

    def propose_block(self,
                      slot: int,
                      state: BeaconState,
                      state_machine: BaseBeaconStateMachine,
                      head_block: BaseBeaconBlock) -> None:
        block = self._make_proposing_block(slot, state, state_machine, head_block)
        self.logger.debug(
            bold_green(f"proposing block, block={block}")
        )
        for _, peer in enumerate(self.peer_pool.connected_nodes.values()):
            self.logger.debug(
                bold_red(f"sending block to peer={peer}")
            )
            peer.sub_proto.send_new_block(block)
        self.chain.import_block(block)

    def _make_proposing_block(self,
                              slot: int,
                              state: BeaconState,
                              state_machine: BaseBeaconStateMachine,
                              parent_block: BaseBeaconBlock) -> BaseBeaconBlock:
        return create_block_on_state(
            state=state,
            config=state_machine.config,
            state_machine=state_machine,
            block_class=SerenityBeaconBlock,
            parent_block=parent_block,
            slot=slot,
            validator_index=self.validator_index,
            privkey=self.privkey,
            attestations=(),
            check_proposer_index=False,
        )

    def skip_block(self,
                   slot: int,
                   state: BeaconState,
                   state_machine: BaseBeaconStateMachine,
                   parent_block: BaseBeaconBlock) -> None:
        post_state = state_machine.state_transition.apply_state_transition_without_block(
            state,
            # TODO: Change back to `slot` instead of `slot + 1`.
            # Currently `apply_state_transition_without_block` only returns the post state
            # of `slot - 1`, so we increment it by one to get the post state of `slot`.
            slot + 1,
            parent_block.root,
        )
        self.logger.debug(
            bold_green(f"skipping block, post state={post_state.root}")
        )
        # FIXME: We might not need to persist state for skip slots since `create_block_on_state`
        # will run the state transition which also includes the state transition for skipped slots.
        self.chain.chaindb.persist_state(post_state)
