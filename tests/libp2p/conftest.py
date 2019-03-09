import asyncio
import os
import subprocess
import time
from typing import (
    NamedTuple,
)

import pytest

from multiaddr import (
    Multiaddr,
    protocols,
)

from libp2p.p2pclient.datastructures import (
    PeerID,
)
from libp2p.p2pclient.p2pclient import (
    Client,
    ConnectionManagerClient,
    ControlClient,
    DHTClient,
    PubSubClient,
)


NUM_P2PDS = 4


@pytest.fixture(scope="module")
def peer_id_random():
    return PeerID.from_base58("QmcgpsyWgH8Y8ajJz1Cu72KnS5uo2Aa2LpzU7kinSupNK1")


@pytest.fixture
def is_control_enabled():
    return False


@pytest.fixture
def is_connmgr_enabled():
    return False


@pytest.fixture
def is_dht_enabled():
    return False


@pytest.fixture
def is_pubsub_enabled():
    return False


class Daemon:
    control_maddr = None
    proc_daemon = None
    log_filename = ""
    f_log = None
    closed = None

    def __init__(
            self,
            control_maddr,
            is_control_enabled,
            is_connmgr_enabled,
            is_dht_enabled,
            is_pubsub_enabled):
        self.control_maddr = control_maddr
        self.is_control_enabled = is_control_enabled
        self.is_connmgr_enabled = is_connmgr_enabled
        self.is_dht_enabled = is_dht_enabled
        self.is_pubsub_enabled = is_pubsub_enabled
        self.is_closed = False
        self._start_logging()
        self._run()

    def _start_logging(self):
        name_control_maddr = str(self.control_maddr).replace('/', '_').replace('.', '_')
        self.log_filename = f'/tmp/log_p2pd{name_control_maddr}.txt'
        self.f_log = open(self.log_filename, 'wb')

    def _run(self):
        cmd_list = [
            "p2pd",
            f"-listen={str(self.control_maddr)}",
        ]
        if self.is_connmgr_enabled:
            cmd_list += [
                "-connManager=true",
                "-connLo=1",
                "-connHi=2",
                "-connGrace=0",
            ]
        if self.is_dht_enabled:
            cmd_list += [
                "-dht=true",
            ]
        if self.is_pubsub_enabled:
            cmd_list += [
                "-pubsub=true",
                "-pubsubRouter=gossipsub",
            ]
        self.proc_daemon = subprocess.Popen(
            cmd_list,
            stdout=self.f_log,
            stderr=self.f_log,
            bufsize=0,
        )

    async def wait_until_ready(self):
        timeout = 10  # seconds
        lines_head_pattern = (
            b'Control socket:',
            b'Peer ID:',
            b'Peer Addrs:',
        )
        lines_head_occurred = {
            line: False
            for line in lines_head_pattern
        }
        t_start = time.time()
        with open(self.log_filename, 'rb') as f_log_read:
            while True:
                is_finished = all([value for _, value in lines_head_occurred.items()])
                if is_finished:
                    break
                if time.time() - t_start > timeout:
                    raise Exception("daemon is not ready before timeout")
                line = f_log_read.readline()
                for head_pattern in lines_head_occurred:
                    if line.startswith(head_pattern):
                        lines_head_occurred[head_pattern] = True
                await asyncio.sleep(0.1)
        # sleep for a while in case that the daemon haven't been ready after emitting these lines
        await asyncio.sleep(0.1)

    def close(self):
        if self.is_closed:
            return
        self.proc_daemon.terminate()
        self.proc_daemon.wait()
        self.f_log.close()
        self.is_closed = True


class DaemonTuple(NamedTuple):
    daemon: Daemon
    client: Client
    control: ControlClient
    connmgr: ConnectionManagerClient
    dht: DHTClient
    pubsub: PubSubClient


class ConnectionFailure(Exception):
    pass


async def make_p2pd_pair_unix(
        serial_no,
        is_control_enabled,
        is_connmgr_enabled,
        is_dht_enabled,
        is_pubsub_enabled):
    control_maddr = Multiaddr(f"/unix/tmp/test_p2pd_control_{serial_no}.sock")
    listen_maddr = Multiaddr(f"/unix/tmp/test_p2pd_listen_{serial_no}.sock")
    # remove the existing unix socket files if they are existing
    try:
        os.unlink(control_maddr.value_for_protocol(protocols.P_UNIX))
    except FileNotFoundError:
        pass
    try:
        os.unlink(listen_maddr.value_for_protocol(protocols.P_UNIX))
    except FileNotFoundError:
        pass
    return await _make_p2pd_pair(
        control_maddr=control_maddr,
        listen_maddr=listen_maddr,
        is_control_enabled=is_control_enabled,
        is_connmgr_enabled=is_connmgr_enabled,
        is_dht_enabled=is_dht_enabled,
        is_pubsub_enabled=is_pubsub_enabled,
    )


async def make_p2pd_pair_ip4(
        serial_no,
        is_control_enabled,
        is_connmgr_enabled,
        is_dht_enabled,
        is_pubsub_enabled):
    base_port = 35566
    num_ports = 2
    control_maddr = Multiaddr(f"/ip4/127.0.0.1/tcp/{base_port+(serial_no*num_ports)}")
    listen_maddr = Multiaddr(f"/ip4/127.0.0.1/tcp/{base_port+(serial_no*num_ports)+1}")
    return await _make_p2pd_pair(
        control_maddr=control_maddr,
        listen_maddr=listen_maddr,
        is_control_enabled=is_control_enabled,
        is_connmgr_enabled=is_connmgr_enabled,
        is_dht_enabled=is_dht_enabled,
        is_pubsub_enabled=is_pubsub_enabled,
    )


async def _make_p2pd_pair(
        control_maddr,
        listen_maddr,
        is_control_enabled,
        is_connmgr_enabled,
        is_dht_enabled,
        is_pubsub_enabled):
    p2pd = Daemon(
        control_maddr=control_maddr,
        is_control_enabled=is_control_enabled,
        is_connmgr_enabled=is_connmgr_enabled,
        is_dht_enabled=is_dht_enabled,
        is_pubsub_enabled=is_pubsub_enabled,
    )
    # wait for daemon ready
    await p2pd.wait_until_ready()
    client = Client(control_maddr)
    controlc = None
    connmgrc = None
    dhtc = None
    pubsubc = None
    if is_control_enabled:
        controlc = ControlClient(client=client, listen_maddr=listen_maddr)
        await controlc.listen()
    if is_connmgr_enabled:
        connmgrc = ConnectionManagerClient(client=client)
    if is_dht_enabled:
        dhtc = DHTClient(client=client)
    if is_pubsub_enabled:
        pubsubc = PubSubClient(client=client)
    return DaemonTuple(
        daemon=p2pd,
        client=client,
        control=controlc,
        connmgr=connmgrc,
        dht=dhtc,
        pubsub=pubsubc,
    )


@pytest.fixture(params=[make_p2pd_pair_ip4, make_p2pd_pair_unix])
async def p2pds(request, is_control_enabled, is_connmgr_enabled, is_dht_enabled, is_pubsub_enabled):
    make_p2pd_pair = request.param
    pairs = tuple(
        asyncio.ensure_future(
            make_p2pd_pair(
                serial_no=i,
                is_control_enabled=is_control_enabled,
                is_connmgr_enabled=is_connmgr_enabled,
                is_dht_enabled=is_dht_enabled,
                is_pubsub_enabled=is_pubsub_enabled,
            )
        )
        for i in range(NUM_P2PDS)
    )
    p2pd_tuples = await asyncio.gather(*pairs)
    yield p2pd_tuples

    # clean up
    for p2pd_tuple in p2pd_tuples:
        if not p2pd_tuple.daemon.is_closed:
            p2pd_tuple.daemon.close()
        if p2pd_tuple.control.listener is not None:
            await p2pd_tuple.control.close()
