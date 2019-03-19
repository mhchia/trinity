import asyncio

import pytest

from trinity.protocol.bcc_libp2p.node import (
    DaemonNode,
)


@pytest.fixture
async def daemon_nodes(controlcs, dhtcs, pubsubcs, connmgrcs):
    nodes = tuple(
        DaemonNode(
            controlc=controlc,
            dhtc=dhtc,
            pubsubc=pubsubc,
            connmgrc=connmgrc
        )
        for controlc, dhtc, pubsubc, connmgrc
        in zip(controlcs, dhtcs, pubsubcs, connmgrcs)
    )
    for node in nodes:
        await node.setup()
    return nodes


async def connect(node0, node1):
    await node0.host.connect(await node1.host.get_peer_info())


@pytest.mark.asyncio
async def test_daemon_node_send_hello_succeeds(daemon_nodes):
    await daemon_nodes[0].send_hello(await daemon_nodes[1].host.get_peer_info())
    await asyncio.sleep(0)
    peers_0 = tuple(
        pinfo.peer_id
        for pinfo in await daemon_nodes[0].host.list_peers()
    )
    assert (await daemon_nodes[1].host.get_id()) in peers_0


@pytest.mark.asyncio
async def test_daemon_node_fails_different_network_id(daemon_nodes, monkeypatch):
    daemon_nodes[1].network_id = 5566
    assert daemon_nodes[0].network_id != daemon_nodes[1].network_id
    await daemon_nodes[0].send_hello(await daemon_nodes[1].host.get_peer_info())
    # yield to the `_handler_hello`
    await asyncio.sleep(0)
    peers_0 = tuple(
        pinfo.peer_id
        for pinfo in await daemon_nodes[0].host.list_peers()
    )
    assert (await daemon_nodes[1].host.get_id()) not in peers_0

