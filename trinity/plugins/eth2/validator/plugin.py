import asyncio
from argparse import (
    ArgumentParser,
    _SubParsersAction,
)
from trinity.endpoint import TrinityEventBusEndpoint
from trinity.extensibility import (
    BaseAsyncStopPlugin,
    BaseIsolatedPlugin,
)

from multiprocessing.managers import (
    BaseManager,
)

from eth.chains.base import (
    BaseChain
)
from trinity.extensibility.events import (
    ResourceAvailableEvent,
)
from trinity.protocol.eth.peer import (
    BaseChainPeerPool,
)
from trinity.plugins.eth2.beacon.beacon_node_bridge import (
    EventBusBeaconNode,
)


class ValidatorPlugin(BaseIsolatedPlugin):

    @property
    def name(self) -> str:
        return "Validator"

    def configure_parser(self, arg_parser: ArgumentParser, subparser: _SubParsersAction) -> None:
        arg_parser.add_argument(
            "--validator",
            action="store_true",
            help="Run as the validator node",
        )

    def on_ready(self, manager_eventbus: TrinityEventBusEndpoint) -> None:
        args = self.context.args
        if args.validator:
            print("!@# onready: in args.validator")
            self.start()

    def do_start(self) -> None:
        loop = asyncio.get_event_loop()
        # trinity_config = self.context.trinity_config
        # self.event_bus.auto_connect_new_announced_endpoints()
        beacon_node = EventBusBeaconNode(self.context.event_bus)
        # TODO:
        #   - Add a `ValidatorService` that print something every N seconds.
        #   - Get access to data/event from `BeaconNode`, through `EventBus` or other ways.
        #   - The service broadcasts a block through `BeaconNode` every N seconds.
        #   - The service broadcasts a block if it finds itself selected as a proposer.
        asyncio.ensure_future(beacon_node.broadcast_block("block123"))
        loop.run_forever()
        loop.close()
