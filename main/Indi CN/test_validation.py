#!/usr/bin/env python3

import re
import sys
import time
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.link import TCLink
from mininet.log import setLogLevel


# ─── QoS CONFIG ─────────────────────────────────────────────

def configure_queues(net):
    s1 = net.get("s1")

    s1.cmd("ovs-vsctl --all destroy QoS")
    s1.cmd("ovs-vsctl --all destroy Queue")

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


# ─── HELPERS ─────────────────────────────────────────────

def extract_ping_rtt(output):
    m = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)", output)
    return float(m.group(1)) if m else None

def extract_iperf_bw(output):
    """More robust parser for iperf / iperf3 output"""
    # Try common patterns first
    patterns = [
        r"([\d.]+)\s+Gbits/sec",
        r"([\d.]+)\s+Mbits/sec",
        r"([\d.]+)\s+Kbits/sec",
        r"([\d.]+)\s+Gbit/sec",
        r"([\d.]+)\s+Mbit/sec",
        r"([\d.]+)\s+Kbit/sec",
    ]
    for pat in patterns:
        m = re.search(pat, output)
        if m:
            val = float(m.group(1))
            if "G" in pat:
                return val * 1000
            elif "K" in pat:
                return val / 1000
            return val

    # Fallback regex (very tolerant)
    m = re.search(r"([\d.]+)\s*([GMK]?)bits?/sec", output, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        unit = m.group(2).upper()
        if unit == "G":
            return val * 1000
        elif unit == "K":
            return val / 1000
        return val

    return None


PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
INFO = "\033[94mINFO\033[0m"


def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}" + (f" – {detail}" if detail else ""))
    return condition


# ─── TOPOLOGY ─────────────────────────────────────────────

def build_test_net():
    net = Mininet(
        switch=OVSSwitch,
        controller=None,
        link=TCLink,
        autoSetMacs=True,
    )

    net.addController("c0", controller=RemoteController,
                      ip="127.0.0.1", port=6633)

    s1 = net.addSwitch("s1", protocols="OpenFlow13")

    hosts = []
    for i in range(1, 5):
        h = net.addHost(f"h{i}",
                        ip=f"10.0.0.{i}/24",
                        mac=f"00:00:00:00:00:0{i}")
        net.addLink(h, s1, delay="2ms")
        hosts.append(h)

    net.start()
    s1.cmd("ovs-vsctl set bridge s1 protocols=OpenFlow13")
    time.sleep(2)

    configure_queues(net)
    return net, hosts, s1


# ─── SCENARIO A ───────────────────────────────────────────

def scenario_a_latency(h1, h2, h3, h4, s1):
    print("\n" + "=" * 60)
    print("SCENARIO A – Latency under load")
    print("=" * 60)

    baseline = extract_ping_rtt(h1.cmd("ping -c 10 10.0.0.2"))

    h4.cmd("iperf -s -p 5001 -u &")
    time.sleep(0.5)
    h3.cmd("iperf -c 10.0.0.4 -p 5001 -u -b 80M -t 10 &")
    time.sleep(1)

    loaded = extract_ping_rtt(h1.cmd("ping -c 10 10.0.0.2"))

    print(f"Baseline RTT: {baseline}")
    print(f"Loaded RTT: {loaded}")

    ok = baseline and loaded and ((loaded - baseline)/baseline < 0.5)

    h3.cmd("kill %iperf")
    h4.cmd("kill %iperf")

    return ok


# ─── SCENARIO B ───────────────────────────────────────────
def scenario_b_throughput(h1, h2, h3, h4, s1):
    print("\n" + "=" * 60)
    print("SCENARIO B – Throughput")
    print("=" * 60)

    # ==================== HIGH PRIORITY (8080) ====================
    print("\n[INFO] Starting HIGH server (8080) on h2")
    h2.cmd("pkill -f 'iperf -s -p 8080' 2>/dev/null || true")  # clean old
    h2.cmd("iperf -s -p 8080 > /dev/null 2>&1 & echo $! > /tmp/h2_iperf.pid")
    time.sleep(2)

    print("[INFO] Running HIGH client on h1")
    high_out = h1.cmd("iperf -c 10.0.0.2 -p 8080 -t 5")
    print(high_out)
    high = extract_iperf_bw(high_out)

    # Kill cleanly
    h2.cmd("kill $(cat /tmp/h2_iperf.pid 2>/dev/null) 2>/dev/null || true")
    h2.cmd("rm -f /tmp/h2_iperf.pid 2>/dev/null || true")

    # ==================== LOW PRIORITY (9999) ====================
    print("\n[INFO] Starting LOW server (9999) on h4")
    h4.cmd("pkill -f 'iperf -s -p 9999' 2>/dev/null || true")
    h4.cmd("iperf -s -p 9999 > /dev/null 2>&1 & echo $! > /tmp/h4_iperf.pid")
    time.sleep(2)

    print("[INFO] Running LOW client on h3")
    low_out = h3.cmd("iperf -c 10.0.0.4 -p 9999 -t 5")
    print(low_out)
    low = extract_iperf_bw(low_out)

    # Kill cleanly
    h4.cmd("kill $(cat /tmp/h4_iperf.pid 2>/dev/null) 2>/dev/null || true")
    h4.cmd("rm -f /tmp/h4_iperf.pid 2>/dev/null || true")

    print(f"\nHIGH: {high} Mbps")
    print(f"LOW : {low} Mbps")

    success = high is not None and low is not None and high >= low
    return success


# ─── MAIN ─────────────────────────────────────────────

if __name__ == "__main__":
    setLogLevel("warning")

    net, hosts, s1 = build_test_net()
    h1, h2, h3, h4 = hosts

    try:
        a = scenario_a_latency(h1, h2, h3, h4, s1)
        b = scenario_b_throughput(h1, h2, h3, h4, s1)

        print("\nRESULT:")
        print("Scenario A:", PASS if a else FAIL)
        print("Scenario B:", PASS if b else FAIL)

        if a and b:
            print("\nALL PASSED ✅")
        else:
            print("\nSOME FAILED ❌")

    finally:
        net.stop()