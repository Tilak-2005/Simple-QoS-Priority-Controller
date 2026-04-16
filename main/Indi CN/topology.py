#!/usr/bin/env python3

import time
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.cli import CLI


def configure_queues(net):
    s1 = net.get("s1")

    s1.cmd("ovs-vsctl --all destroy QoS")
    s1.cmd("ovs-vsctl --all destroy Queue")

    # ✅ Correct queue creation
    q0 = s1.cmd("ovs-vsctl create Queue other-config:max-rate=60000000").strip()
    q1 = s1.cmd("ovs-vsctl create Queue other-config:max-rate=30000000").strip()
    q2 = s1.cmd("ovs-vsctl create Queue other-config:max-rate=10000000").strip()
    q3 = s1.cmd("ovs-vsctl create Queue other-config:max-rate=1000000").strip()

    qos = s1.cmd(f"""
ovs-vsctl create QoS type=linux-htb other-config:max-rate=100000000 \
queues=0={q0},1={q1},2={q2},3={q3}
""").strip()

    for intf in s1.intfNames():
        if intf != "lo":
            s1.cmd(f"ovs-vsctl set port {intf} qos={qos}")


def build_topology():
    net = Mininet(
        switch=OVSSwitch,
        controller=None,
        link=TCLink,
        autoSetMacs=True,
    )

    net.addController("c0", controller=RemoteController,
                      ip="127.0.0.1", port=6633)

    s1 = net.addSwitch("s1", protocols="OpenFlow13")

    for i in range(1, 5):
        h = net.addHost(f"h{i}",
                        ip=f"10.0.0.{i}/24",
                        mac=f"00:00:00:00:00:0{i}")
        net.addLink(h, s1, delay="2ms")

    net.start()
    s1.cmd("ovs-vsctl set bridge s1 protocols=OpenFlow13")
    time.sleep(2)

    configure_queues(net)

    CLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    build_topology()