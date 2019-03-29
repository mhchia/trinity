import asyncio
from argparse import (
    ArgumentParser,
    _SubParsersAction,
)
from p2p import ecies
from p2p.constants import DEFAULT_MAX_PEERS
from trinity._utils.shutdown import (
    exit_with_service_and_endpoint,
)
from trinity.config import BeaconAppConfig
from trinity.endpoint import TrinityEventBusEndpoint
from trinity.extensibility import BaseIsolatedPlugin
from trinity.plugins.eth2.beacon.beacon_node_bridge import (
    BeaconNodeEventBusHandler,
)
from trinity.server import BCCServer
from trinity.sync.beacon.chain import BeaconChainSyncer

from trinity.db.beacon.manager import (
    create_db_consumer_manager
)


class BeaconNodePlugin(BaseIsolatedPlugin):

    handler: BeaconNodeEventBusHandler

    @property
    def name(self) -> str:
        return "Beacon Node"

    def configure_parser(self, arg_parser: ArgumentParser, subparser: _SubParsersAction) -> None:
        arg_parser.add_argument(
            "--bootstrap_nodes",
            help="enode://node1@0.0.0.0:1234,enode://node2@0.0.0.0:5678",
        )
        arg_parser.add_argument(
            "--beacon-nodekey",
            help="0xabcd",
        )

    def on_ready(self, manager_eventbus: TrinityEventBusEndpoint) -> None:
        if self.context.trinity_config.has_app_config(BeaconAppConfig):
            self.start()

    def do_start(self) -> None:
        trinity_config = self.context.trinity_config
        beacon_config = trinity_config.get_app_config(BeaconAppConfig)

        db_manager = create_db_consumer_manager(trinity_config.database_ipc_path)
        base_db = db_manager.get_db()  # type: ignore
        chain_db = db_manager.get_chaindb()  # type: ignore
        chain_config = beacon_config.get_chain_config()
        chain = chain_config.initialize_chain(base_db)

        if self.context.args.beacon_nodekey:
            from eth_keys.datatypes import PrivateKey
            privkey = PrivateKey(bytes.fromhex(self.context.args.beacon_nodekey))
        else:
            privkey = ecies.generate_privkey()

        server = BCCServer(
            privkey=privkey,
            port=self.context.args.port,
            chain=chain,
            chaindb=chain_db,
            headerdb=None,
            base_db=base_db,
            network_id=trinity_config.network_id,
            max_peers=DEFAULT_MAX_PEERS,
            bootstrap_nodes=None,
            preferred_nodes=None,
            event_bus=self.context.event_bus,
            token=None,
        )
        self.handler = BeaconNodeEventBusHandler(server, self.context.event_bus)
        print(f"!@# self.context.event_bus.name = {self.context.event_bus.name}")

        syncer = BeaconChainSyncer(
            chain_db,
            server.peer_pool,
            server.cancel_token,
        )
        # slot = SlotTicker
        # if args.validator:
        #     validator = Validator

        loop = asyncio.get_event_loop()
        asyncio.ensure_future(exit_with_service_and_endpoint(server, self.context.event_bus))
        asyncio.ensure_future(server.run())
        asyncio.ensure_future(self.handler.run())
        # if args.validator:
        #     asyncio.ensure_future(validator.run())
        asyncio.ensure_future(syncer.run())
        loop.run_forever()
        loop.close()
