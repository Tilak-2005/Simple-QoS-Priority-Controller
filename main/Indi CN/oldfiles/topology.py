# #!/usr/bin/env python3
# """
# QoS Mininet Topology
# ====================
# Linear 4-host topology with a single OVS switch.
# Hosts are intentionally placed on different subnets of 10.0.0.0/24 to make
# Wireshark captures easy to read.

#       h1 (10.0.0.1)  ─┐
#       h2 (10.0.0.2)  ─┤  s1 (OVS)  ── Ryu controller (6633)
#       h3 (10.0.0.3)  ─┤
#       h4 (10.0.0.4)  ─┘

# Queues (OVSDB / HTB):
#   Queue 0 – CRITICAL  rate=10Mbps  (ICMP)
#   Queue 1 – HIGH      rate=5Mbps   (SSH/DNS/HTTP)
#   Queue 2 – MEDIUM    rate=3Mbps   (iperf bulk)
#   Queue 3 – LOW       rate=1Mbps   (best-effort)

# Usage:
#   sudo python3 topology.py

# Prerequisites:
#   sudo pip3 install mininet ryu
# """

# import sys
# import time
# from mininet.net import Mininet
# from mininet.node import OVSSwitch, RemoteController
# from mininet.link import TCLink
# from mininet.log import setLogLevel, info
# from mininet.cli import CLI


# # Queue bandwidth settings (bps)
# QUEUE_RATES = {
#     0: 10_000_000,   # CRITICAL  10 Mbps
#     1:  5_000_000,   # HIGH       5 Mbps
#     2:  3_000_000,   # MEDIUM     3 Mbps
#     3:  1_000_000,   # LOW        1 Mbps
# }

# CONTROLLER_IP   = "127.0.0.1"
# CONTROLLER_PORT = 6633


# def configure_queues(net):
#     """
#     Configure OVS queues via ovs-vsctl so the controller's set_queue
#     action maps to real HTB bandwidth limits.
#     """
#     info("*** Configuring QoS queues on s1\n")
#     s1 = net.get("s1")

#     # Build the queue list string for ovs-vsctl
#     queues_arg = " -- ".join(
#         f"create Queue other-config:min-rate={r} other-config:max-rate={r}"
#         for r in QUEUE_RATES.values()
#     )
#     result = s1.cmd(f"ovs-vsctl {queues_arg}")
#     queue_uuids = result.strip().split()

#     if len(queue_uuids) != 4:
#         info(f"[WARN] Expected 4 queue UUIDs, got: {queue_uuids}\n")
#         return

#     q_str = "[" + ",".join(queue_uuids) + "]"
#     qos_uuid = s1.cmd(
#         f"ovs-vsctl create QoS type=linux-htb queues={q_str}"
#     ).strip()

#     # Apply QoS to every port on s1
#     for intf in s1.intfNames():
#         if intf != "lo":
#             s1.cmd(f"ovs-vsctl set port {intf} qos={qos_uuid}")
#             info(f"    QoS applied to {intf}\n")


# def build_topology():
#     info("*** Starting Mininet QoS topology\n")
#     net = Mininet(
#         switch=OVSSwitch,
#         controller=None,
#         link=TCLink,
#         autoSetMacs=True,
#     )

#     info("*** Adding Ryu controller\n")
#     c0 = net.addController(
#         "c0",
#         controller=RemoteController,
#         ip=CONTROLLER_IP,
#         port=CONTROLLER_PORT,
#     )

#     info("*** Adding switch\n")
#     s1 = net.addSwitch("s1", protocols="OpenFlow13")

#     info("*** Adding hosts\n")
#     hosts = []
#     for i in range(1, 5):
#         h = net.addHost(
#             f"h{i}",
#             ip=f"10.0.0.{i}/24",
#             mac=f"00:00:00:00:00:0{i}",
#         )
#         # 100 Mbps uplink with 2ms base delay
#         net.addLink(h, s1, bw=100, delay="2ms", use_htb=True)
#         hosts.append(h)

#     info("*** Starting network\n")
#     net.start()

#     info("*** Configuring OVS switch\n")
#     s1.cmd("ovs-vsctl set bridge s1 protocols=OpenFlow13")

#     # Give controller a moment to connect
#     time.sleep(2)

#     configure_queues(net)

#     info("\n*** Topology ready\n")
#     info("    Hosts: h1=10.0.0.1  h2=10.0.0.2  h3=10.0.0.3  h4=10.0.0.4\n")
#     info("    Controller: Ryu at %s:%d\n" % (CONTROLLER_IP, CONTROLLER_PORT))
#     info("\n*** Try these test commands in the Mininet CLI:\n")
#     info("    h1 ping -c4 h2              # CRITICAL – ICMP\n")
#     info("    h1 iperf -s -p 5001 &  then  h2 iperf -c 10.0.0.1 -p 5001 -t5 # MEDIUM\n")
#     info("    h3 iperf -s -p 8080 &  then  h4 iperf -c 10.0.0.3 -p 8080 -t5 # LOW\n")
#     info("    s1 ovs-ofctl -O OpenFlow13 dump-flows s1   # inspect flow table\n")

#     CLI(net)

#     info("*** Stopping network\n")
#     net.stop()


# if __name__ == "__main__":
#     setLogLevel("info")
#     build_topology()


#!/usr/bin/env python3

#!/usr/bin/env python3

import time
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.cli import CLI

CONTROLLER_IP = "127.0.0.1"
CONTROLLER_PORT = 6633


def configure_queues(net):
    """
    Configure OVS queues with STRICT QoS (FINAL FIX)
    """
    info("*** Configuring QoS queues on s1\n")
    s1 = net.get("s1")

    # 🔴 Clean old QoS
    s1.cmd("ovs-vsctl --all destroy QoS")
    s1.cmd("ovs-vsctl --all destroy Queue")

    # 🟢 Create queues (STRICT max-rate + r2q)
    s1.cmd("""
    ovs-vsctl \
    -- --id=@q0 create Queue other-config:max-rate=60000000 \
    -- --id=@q1 create Queue other-config:max-rate=30000000 \
    -- --id=@q2 create Queue other-config:max-rate=10000000 \
    -- --id=@q3 create Queue other-config:max-rate=1000000 \
    -- --id=@newqos create QoS type=linux-htb \
       other-config:max-rate=100000000 other-config:r2q=10 \
       queues=0=@q0,1=@q1,2=@q2,3=@q3
    """)

    # 🔥 APPLY QoS ONLY ON EGRESS PORTS (CRITICAL FIX)
    for intf in ["s1-eth2", "s1-eth4"]:
        s1.cmd(f"ovs-vsctl set port {intf} qos=@newqos")
        info(f"    QoS applied to {intf}\n")


def build_topology():
    info("*** Starting Mininet QoS topology\n")

    net = Mininet(
        switch=OVSSwitch,
        controller=None,
        link=TCLink,
        autoSetMacs=True,
    )

    info("*** Adding Ryu controller\n")
    net.addController(
        "c0",
        controller=RemoteController,
        ip=CONTROLLER_IP,
        port=CONTROLLER_PORT,
    )

    info("*** Adding switch\n")
    s1 = net.addSwitch("s1", protocols="OpenFlow13")

    info("*** Adding hosts\n")
    for i in range(1, 5):
        h = net.addHost(
            f"h{i}",
            ip=f"10.0.0.{i}/24",
            mac=f"00:00:00:00:00:0{i}",
        )
        # net.addLink(h, s1, bw=100, delay="2ms", use_htb=True)
        net.addLink(h, s1, delay="2ms")

    info("*** Starting network\n")
    net.start()

    info("*** Configuring OVS switch\n")
    s1.cmd("ovs-vsctl set bridge s1 protocols=OpenFlow13")

    time.sleep(2)

    configure_queues(net)

    info("\n*** Topology ready\n")
    CLI(net)

    info("*** Stopping network\n")
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    build_topology()