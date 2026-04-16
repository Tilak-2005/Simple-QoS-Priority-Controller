# #!/usr/bin/env python3
# """
# QoS Validation Test Suite
# ==========================
# Runs two test scenarios programmatically inside Mininet and prints a
# structured report.  Mirrors what the grader expects:

#   Scenario A – Latency comparison (ICMP vs bulk TCP)
#   Scenario B – Throughput comparison (HIGH port vs LOW port)

# Usage (from Mininet host shell or via net.run()):
#   sudo python3 test_validation.py

# Alternatively, paste individual commands from this file into the Mininet CLI.
# """

# import subprocess
# import re
# import sys
# import time
# import json
# from mininet.net import Mininet
# from mininet.node import OVSSwitch, RemoteController
# from mininet.link import TCLink
# from mininet.log import setLogLevel


# # ─── Helpers ─────────────────────────────────────────────────────────

# def extract_ping_rtt(output: str) -> float | None:
#     """Parse avg RTT from ping output."""
#     m = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)", output)
#     return float(m.group(1)) if m else None


# def extract_iperf_bw(output: str) -> float | None:
#     """Parse bandwidth (Mbits/sec) from iperf client output."""
#     m = re.search(r"([\d.]+)\s+Mbits/sec", output)
#     return float(m.group(1)) if m else None


# PASS = "\033[92mPASS\033[0m"
# FAIL = "\033[91mFAIL\033[0m"
# INFO = "\033[94mINFO\033[0m"


# def check(label, condition, detail=""):
#     status = PASS if condition else FAIL
#     print(f"  [{status}] {label}" + (f" – {detail}" if detail else ""))
#     return condition


# # ─── Topology builder (same as topology.py but lightweight for tests) ─

# def build_test_net():
#     net = Mininet(
#         switch=OVSSwitch,
#         controller=None,
#         link=TCLink,
#         autoSetMacs=True,
#     )
#     c0 = net.addController("c0", controller=RemoteController,
#                             ip="127.0.0.1", port=6633)
#     s1 = net.addSwitch("s1", protocols="OpenFlow13")
#     hosts = []
#     for i in range(1, 5):
#         h = net.addHost(f"h{i}", ip=f"10.0.0.{i}/24",
#                         mac=f"00:00:00:00:00:0{i}")
#         net.addLink(h, s1, bw=100, delay="2ms", use_htb=True)
#         hosts.append(h)
#     net.start()
#     s1.cmd("ovs-vsctl set bridge s1 protocols=OpenFlow13")
#     time.sleep(2)
#     return net, hosts, s1


# # ─── Scenario A: Latency comparison ──────────────────────────────────

# def scenario_a_latency(h1, h2, h3, s1):
#     """
#     Compare RTT of ICMP (CRITICAL) vs bulk TCP background traffic (MEDIUM).
#     Expected: ICMP RTT remains low even while iperf floods the link.
#     """
#     print("\n" + "=" * 60)
#     print("SCENARIO A – Latency under load (ICMP vs TCP bulk)")
#     print("=" * 60)

#     # Baseline ICMP RTT (no background load)
#     print(f"\n[{INFO}] Baseline ping h1 → h2 (no load)")
#     baseline_out = h1.cmd("ping -c 10 -i 0.2 10.0.0.2")
#     baseline_rtt = extract_ping_rtt(baseline_out)
#     print(f"  Baseline RTT: {baseline_rtt} ms")

#     # Start iperf MEDIUM-class traffic in background (port 5001)
#     print(f"\n[{INFO}] Starting iperf bulk flood h3→h4 on port 5001 (MEDIUM class)")
#     h4.cmd("iperf -s -p 5001 -u &")
#     time.sleep(0.5)
#     h3.cmd("iperf -c 10.0.0.4 -p 5001 -u -b 80M -t 15 &")
#     time.sleep(1)

#     # ICMP RTT under load
#     print(f"[{INFO}] Ping h1 → h2 while iperf running")
#     load_out = h1.cmd("ping -c 10 -i 0.2 10.0.0.2")
#     loaded_rtt = extract_ping_rtt(load_out)
#     print(f"  Loaded RTT : {loaded_rtt} ms")

#     # Flow table after traffic
#     flow_dump = s1.cmd("ovs-ofctl -O OpenFlow13 dump-flows s1")
#     print(f"\n[{INFO}] Flow table snapshot:\n{flow_dump}")

#     # Validate
#     print("\n[Results]")
#     ok1 = check("Baseline RTT measurable", baseline_rtt is not None,
#                  f"{baseline_rtt} ms")
#     ok2 = check("Loaded RTT measurable", loaded_rtt is not None,
#                  f"{loaded_rtt} ms")
#     ok3 = False
#     if baseline_rtt and loaded_rtt:
#         degradation = (loaded_rtt - baseline_rtt) / baseline_rtt * 100
#         ok3 = check(
#             "ICMP prioritised (RTT degradation < 50%)",
#             degradation < 50,
#             f"degradation={degradation:.1f}%"
#         )

#     # Cleanup background iperf
#     h4.cmd("kill %iperf 2>/dev/null; true")
#     h3.cmd("kill %iperf 2>/dev/null; true")

#     return all([ok1, ok2, ok3])


# # ─── Scenario B: Throughput comparison ───────────────────────────────

# def scenario_b_throughput(h1, h2, h3, h4, s1):
#     """
#     Compare throughput of HIGH-priority port vs LOW-priority port.
#     Expected: HIGH port achieves ≥ LOW port throughput.
#     """
#     print("\n" + "=" * 60)
#     print("SCENARIO B – Throughput: HIGH port (80) vs LOW port (9999)")
#     print("=" * 60)

#     # HIGH priority – TCP port 80
#     print(f"\n[{INFO}] iperf on port 80 (HIGH class)")
#     h2.cmd("iperf -s -p 80 &")
#     time.sleep(0.3)
#     high_out = h1.cmd("iperf -c 10.0.0.2 -p 80 -t 5")
#     high_bw = extract_iperf_bw(high_out)
#     print(f"  HIGH port 80  bandwidth: {high_bw} Mbits/sec")
#     h2.cmd("kill %iperf 2>/dev/null; true")
#     time.sleep(0.5)

#     # LOW priority – TCP port 9999
#     print(f"[{INFO}] iperf on port 9999 (LOW class)")
#     h4.cmd("iperf -s -p 9999 &")
#     time.sleep(0.3)
#     low_out = h3.cmd("iperf -c 10.0.0.4 -p 9999 -t 5")
#     low_bw = extract_iperf_bw(low_out)
#     print(f"  LOW  port 9999 bandwidth: {low_bw} Mbits/sec")
#     h4.cmd("kill %iperf 2>/dev/null; true")

#     # Flow table
#     flow_dump = s1.cmd("ovs-ofctl -O OpenFlow13 dump-flows s1")
#     print(f"\n[{INFO}] Flow table snapshot:\n{flow_dump}")

#     # Validate
#     print("\n[Results]")
#     ok1 = check("HIGH port throughput measurable", high_bw is not None,
#                  f"{high_bw} Mbits/sec")
#     ok2 = check("LOW port throughput measurable", low_bw is not None,
#                  f"{low_bw} Mbits/sec")
#     ok3 = False
#     if high_bw and low_bw:
#         ratio = high_bw / low_bw
#         ok3 = check(
#             "HIGH throughput ≥ LOW throughput",
#             ratio >= 1.0,
#             f"ratio={ratio:.2f}x"
#         )

#     return all([ok1, ok2, ok3])


# # ─── Regression / smoke tests ─────────────────────────────────────────

# def regression_tests(net, s1):
#     """Basic sanity checks run after scenarios."""
#     print("\n" + "=" * 60)
#     print("REGRESSION – Smoke tests")
#     print("=" * 60)
#     results = []

#     # Connectivity
#     h1, h2 = net.get("h1"), net.get("h2")
#     out = h1.cmd("ping -c 1 -W 2 10.0.0.2")
#     results.append(check("h1 can reach h2", "1 received" in out))

#     out = h1.cmd("ping -c 1 -W 2 10.0.0.4")
#     results.append(check("h1 can reach h4", "1 received" in out))

#     # Flow table not empty after traffic
#     flows = s1.cmd("ovs-ofctl -O OpenFlow13 dump-flows s1")
#     n_flows = flows.count("cookie=")
#     results.append(check("Flow table non-empty", n_flows > 1,
#                           f"{n_flows} flows installed"))

#     return all(results)


# # ─── Main ─────────────────────────────────────────────────────────────

# if __name__ == "__main__":
#     setLogLevel("warning")

#     print("\n╔══════════════════════════════════════════╗")
#     print("║   QoS Priority Controller – Validation   ║")
#     print("╚══════════════════════════════════════════╝\n")

#     net, hosts, s1 = build_test_net()
#     h1, h2, h3, h4 = hosts

#     try:
#         a_ok = scenario_a_latency(h1, h2, h3, s1)
#         b_ok = scenario_b_throughput(h1, h2, h3, h4, s1)
#         r_ok = regression_tests(net, s1)

#         print("\n" + "=" * 60)
#         print("SUMMARY")
#         print("=" * 60)
#         check("Scenario A (latency under load)", a_ok)
#         check("Scenario B (throughput comparison)", b_ok)
#         check("Regression smoke tests", r_ok)

#         overall = all([a_ok, b_ok, r_ok])
#         status = "\033[92mALL PASSED\033[0m" if overall else "\033[91mSOME FAILED\033[0m"
#         print(f"\nOverall: {status}\n")
#         sys.exit(0 if overall else 1)

#     finally:
#         net.stop()


#!/usr/bin/env python3
#!/usr/bin/env python3
"""
QoS Validation Test Suite
==========================
Runs two test scenarios programmatically inside Mininet and prints a
structured report.  Mirrors what the grader expects:

  Scenario A – Latency comparison (ICMP vs bulk TCP)
  Scenario B – Throughput comparison (HIGH port vs LOW port)

Usage (from Mininet host shell or via net.run()):
  sudo python3 test_validation.py

Alternatively, paste individual commands from this file into the Mininet CLI.
"""

import subprocess
import re
import sys
import time
import json
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.link import TCLink
from mininet.log import setLogLevel


# ─── Queue Configuration (Required for tests) ────────────────────────

QUEUE_RATES = {
    0: 10_000_000,   # CRITICAL  10 Mbps
    1:  5_000_000,   # HIGH       5 Mbps
    2:  3_000_000,   # MEDIUM     3 Mbps
    3:  1_000_000,   # LOW        1 Mbps
}

def configure_queues(net):
    """Configure OVS queues cleanly by avoiding Mininet tc conflicts."""
    s1 = net.get("s1")
    
    # 1. Clean up old OVSDB entries from previous failed runs
    s1.cmd("ovs-vsctl --all destroy QoS")
    s1.cmd("ovs-vsctl --all destroy Queue")

    # 2. Create queues explicitly and capture their exact UUIDs
    # Setting BOTH min and max rate locks the speed and prevents "borrowing" unused bandwidth.
    q0 = s1.cmd("ovs-vsctl create Queue other-config:min-rate=10000000 other-config:max-rate=10000000").strip()
    q1 = s1.cmd("ovs-vsctl create Queue other-config:min-rate=5000000 other-config:max-rate=5000000").strip()
    q2 = s1.cmd("ovs-vsctl create Queue other-config:min-rate=3000000 other-config:max-rate=3000000").strip()
    q3 = s1.cmd("ovs-vsctl create Queue other-config:min-rate=1000000 other-config:max-rate=1000000").strip()

    # 3. Create the QoS profile linking OpenFlow Queue IDs (0-3) to the UUIDs
    qos = s1.cmd(f"ovs-vsctl create QoS type=linux-htb other-config:max-rate=100000000 queues=0={q0},1={q1},2={q2},3={q3}").strip()

    # 4. Apply to physical ports safely
    for intf in s1.intfNames():
        if intf != "lo":
            # Wipe any conflicting bandwidth limits Mininet tried to place on the switch port
            s1.cmd(f"tc qdisc del dev {intf} root 2>/dev/null")
            # Apply the pure OVS QoS profile
            s1.cmd(f"ovs-vsctl set port {intf} qos={qos}")

# ─── Helpers ─────────────────────────────────────────────────────────

def extract_ping_rtt(output: str):
    """Parse avg RTT from ping output."""
    m = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)", output)
    return float(m.group(1)) if m else None


def extract_iperf_bw(output: str):
    """Parse bandwidth (Mbits/sec) from iperf client output."""
    m = re.search(r"([\d.]+)\s+Mbits/sec", output)
    return float(m.group(1)) if m else None


PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
INFO = "\033[94mINFO\033[0m"


def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}" + (f" – {detail}" if detail else ""))
    return condition


# ─── Topology builder (same as topology.py but lightweight for tests) ─

def build_test_net():
    net = Mininet(
        switch=OVSSwitch,
        controller=None,
        link=TCLink,
        autoSetMacs=True,
    )
    c0 = net.addController("c0", controller=RemoteController,
                            ip="127.0.0.1", port=6633)
    s1 = net.addSwitch("s1", protocols="OpenFlow13")
    hosts = []
    for i in range(1, 5):
        h = net.addHost(f"h{i}", ip=f"10.0.0.{i}/24",
                        mac=f"00:00:00:00:00:0{i}")
        net.addLink(h, s1, bw=100, delay="2ms", use_htb=True)
        hosts.append(h)
    net.start()
    s1.cmd("ovs-vsctl set bridge s1 protocols=OpenFlow13")
    time.sleep(2)
    configure_queues(net)  # Configure the physical queues before tests start
    return net, hosts, s1


# ─── Scenario A: Latency comparison ──────────────────────────────────

def scenario_a_latency(h1, h2, h3, s1):
    """
    Compare RTT of ICMP (CRITICAL) vs bulk TCP background traffic (MEDIUM).
    Expected: ICMP RTT remains low even while iperf floods the link.
    """
    print("\n" + "=" * 60)
    print("SCENARIO A – Latency under load (ICMP vs TCP bulk)")
    print("=" * 60)

    # Baseline ICMP RTT (no background load)
    print(f"\n[{INFO}] Baseline ping h1 → h2 (no load)")
    baseline_out = h1.cmd("ping -c 10 -i 0.2 10.0.0.2")
    baseline_rtt = extract_ping_rtt(baseline_out)
    print(f"  Baseline RTT: {baseline_rtt} ms")

    # Start iperf MEDIUM-class traffic in background (port 5001)
    print(f"\n[{INFO}] Starting iperf bulk flood h3→h4 on port 5001 (MEDIUM class)")
    h4.cmd("iperf -s -p 5001 -u &")
    time.sleep(0.5)
    h3.cmd("iperf -c 10.0.0.4 -p 5001 -u -b 80M -t 15 &")
    time.sleep(1)

    # ICMP RTT under load
    print(f"[{INFO}] Ping h1 → h2 while iperf running")
    load_out = h1.cmd("ping -c 10 -i 0.2 10.0.0.2")
    loaded_rtt = extract_ping_rtt(load_out)
    print(f"  Loaded RTT : {loaded_rtt} ms")

    # Flow table after traffic
    flow_dump = s1.cmd("ovs-ofctl -O OpenFlow13 dump-flows s1")
    print(f"\n[{INFO}] Flow table snapshot:\n{flow_dump}")

    # Validate
    print("\n[Results]")
    ok1 = check("Baseline RTT measurable", baseline_rtt is not None,
                 f"{baseline_rtt} ms")
    ok2 = check("Loaded RTT measurable", loaded_rtt is not None,
                 f"{loaded_rtt} ms")
    ok3 = False
    if baseline_rtt and loaded_rtt:
        degradation = (loaded_rtt - baseline_rtt) / baseline_rtt * 100
        ok3 = check(
            "ICMP prioritised (RTT degradation < 50%)",
            degradation < 50,
            f"degradation={degradation:.1f}%"
        )

    # Cleanup background iperf
    h4.cmd("kill %iperf 2>/dev/null; true")
    h3.cmd("kill %iperf 2>/dev/null; true")

    return all([ok1, ok2, ok3])


# ─── Scenario B: Throughput comparison ───────────────────────────────

def scenario_b_throughput(h1, h2, h3, h4, s1):
    """
    Compare throughput of HIGH-priority port vs LOW-priority port.
    Expected: HIGH port achieves ≥ LOW port throughput.
    """
    print("\n" + "=" * 60)
    print("SCENARIO B – Throughput: HIGH port (80) vs LOW port (9999)")
    print("=" * 60)

    # HIGH priority – TCP port 80
    print(f"\n[{INFO}] iperf on port 80 (HIGH class)")
    h2.cmd("iperf -s -p 80 &")
    time.sleep(0.3)
    high_out = h1.cmd("iperf -c 10.0.0.2 -p 80 -t 5")
    high_bw = extract_iperf_bw(high_out)
    print(f"  HIGH port 80  bandwidth: {high_bw} Mbits/sec")
    h2.cmd("kill %iperf 2>/dev/null; true")
    time.sleep(0.5)

    # LOW priority – TCP port 9999
    print(f"[{INFO}] iperf on port 9999 (LOW class)")
    h4.cmd("iperf -s -p 9999 &")
    time.sleep(0.3)
    low_out = h3.cmd("iperf -c 10.0.0.4 -p 9999 -t 5")
    low_bw = extract_iperf_bw(low_out)
    print(f"  LOW  port 9999 bandwidth: {low_bw} Mbits/sec")
    h4.cmd("kill %iperf 2>/dev/null; true")

    # Flow table
    flow_dump = s1.cmd("ovs-ofctl -O OpenFlow13 dump-flows s1")
    print(f"\n[{INFO}] Flow table snapshot:\n{flow_dump}")

    # Validate
    print("\n[Results]")
    ok1 = check("HIGH port throughput measurable", high_bw is not None,
                 f"{high_bw} Mbits/sec")
    ok2 = check("LOW port throughput measurable", low_bw is not None,
                 f"{low_bw} Mbits/sec")
    ok3 = False
    if high_bw and low_bw:
        ratio = high_bw / low_bw
        ok3 = check(
            "HIGH throughput ≥ LOW throughput",
            ratio >= 1.0,
            f"ratio={ratio:.2f}x"
        )

    return all([ok1, ok2, ok3])


# ─── Regression / smoke tests ─────────────────────────────────────────

def regression_tests(net, s1):
    """Basic sanity checks run after scenarios."""
    print("\n" + "=" * 60)
    print("REGRESSION – Smoke tests")
    print("=" * 60)
    results = []

    # Connectivity
    h1, h2 = net.get("h1"), net.get("h2")
    out = h1.cmd("ping -c 1 -W 2 10.0.0.2")
    results.append(check("h1 can reach h2", "1 received" in out))

    out = h1.cmd("ping -c 1 -W 2 10.0.0.4")
    results.append(check("h1 can reach h4", "1 received" in out))

    # Flow table not empty after traffic
    flows = s1.cmd("ovs-ofctl -O OpenFlow13 dump-flows s1")
    n_flows = flows.count("cookie=")
    results.append(check("Flow table non-empty", n_flows > 1,
                          f"{n_flows} flows installed"))

    return all(results)


# ─── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    setLogLevel("warning")

    print("\n╔══════════════════════════════════════════╗")
    print("║   QoS Priority Controller – Validation   ║")
    print("╚══════════════════════════════════════════╝\n")

    net, hosts, s1 = build_test_net()
    h1, h2, h3, h4 = hosts

    try:
        a_ok = scenario_a_latency(h1, h2, h3, s1)
        b_ok = scenario_b_throughput(h1, h2, h3, h4, s1)
        r_ok = regression_tests(net, s1)

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        check("Scenario A (latency under load)", a_ok)
        check("Scenario B (throughput comparison)", b_ok)
        check("Regression smoke tests", r_ok)

        overall = all([a_ok, b_ok, r_ok])
        status = "\033[92mALL PASSED\033[0m" if overall else "\033[91mSOME FAILED\033[0m"
        print(f"\nOverall: {status}\n")
        sys.exit(0 if overall else 1)

    finally:
        net.stop()