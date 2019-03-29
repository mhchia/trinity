import asyncio
from typing import (
    Type,
    TypeVar,
)

from cancel_token import (
    CancelToken,
)
from lahja import (
    BaseEvent,
    BaseRequestResponseEvent,
    BroadcastConfig,
)

from trinity.constants import (
    TO_NETWORKING_BROADCAST_CONFIG,
)
from trinity.endpoint import (
    TrinityEventBusEndpoint,
)
from trinity.server import BCCServer
from p2p.service import (
    BaseService,
)


class BaseBeaconNodeResponse(BaseEvent):

    def __init__(self, error: Exception) -> None:
        self.error = error


class BroadcastBlockResponse(BaseBeaconNodeResponse):
    pass


class BroadcastBlockRequest(BaseRequestResponseEvent[BroadcastBlockResponse]):

    def __init__(self, block: str) -> None:
        self.block = block

    @staticmethod
    def expected_response_type() -> Type[BroadcastBlockResponse]:
        return BroadcastBlockResponse


class BeaconNodeEventBusHandler(BaseService):
    """
    The ``BeaconNodeEventBusHandler`` listens for certain events on the eventbus and
    delegates them to the ``BCCServer`` to get answers. It then propagates responses
    back to the caller.
    """
    def __init__(self,
                 server: BCCServer,
                 event_bus: TrinityEventBusEndpoint,
                 token: CancelToken = None) -> None:
        super().__init__(token)
        self.server = server
        self.event_bus = event_bus

    async def _run(self) -> None:
        self.logger.info("Running BeaconNodeEventBusHandler")

        self.run_daemon_task(self.handle_broadcast_block())
        await self.cancel_token.wait()

    async def handle_broadcast_block(self) -> None:
        print("!@# handle_broadcast_block: begin")
        async for event in self.wait_iter(self.event_bus.stream(BroadcastBlockRequest)):
            # do nothing
            print(f"!@# handle_broadcast_block: new event {event}")
            error = None
            self.event_bus.broadcast(
                event.expected_response_type()(error),
                event.broadcast_config(),
            )
        print("!@# handle_broadcast_block: end")


TResponse = TypeVar("TResponse", bound=BaseBeaconNodeResponse)


class EventBusBeaconNode:
    def __init__(self, event_bus: TrinityEventBusEndpoint) -> None:
        self.event_bus = event_bus

    async def broadcast_block(self, block: str) -> None:
        event = BroadcastBlockRequest(block)
        print("!@# broadcast_block: begin")

        # Commented out the following code snippet for now.
        # My own guess: it seems we need to wait until the `event_bus` are connected, to ensure
        #   `event_bus.request` works? Need to investigate deeper.

        while True:
            if self.event_bus.is_connected_to('bbeacon-node'):
                print("!@# connected to `bbeacon-node`")
                break
            else:
                print("!@# not connected to `bbeacon-node`, wait")
            await asyncio.sleep(0.01)

        resp = await self.event_bus.request(
            event,
            BroadcastConfig(filter_endpoint='bbeacon-node'),
            # BroadcastConfig(),  # this works as well
        )
        print(f"!@# broadcast_block: resp={resp}")
        self._pass_or_raise(resp)
        print("!@# broadcast_block: end")

    def _pass_or_raise(self, response: TResponse) -> TResponse:
        if response.error is not None:
            print("!@# _pass_or_raise: raise")
            raise response.error

        print("!@# _pass_or_raise: pass")
        return response
