# SDN QoS Priority Controller

> **Orange Student Project** — Mininet + Ryu OpenFlow 1.3  
> Demonstrates traffic classification, priority scheduling, and measurable latency/throughput impact.

---

## Problem Statement

Standard switched networks treat all traffic equally (best-effort). A video call competes with a bulk file transfer for the same bandwidth. SDN's programmable control plane lets us fix this: the controller inspects each flow's characteristics and installs match-action rules that enforce priority queuing across the data plane.

**Goal:** Build a Ryu controller that:
1. Classifies traffic into four priority classes (CRITICAL → HIGH → MEDIUM → LOW)
2. Installs OpenFlow flow rules that map each class to a dedicated HTB queue
3. Demonstrates measurable latency and throughput differences between classes

---

## Architecture

```
┌─────────────────────────────────────┐
│         Ryu Controller              │
│  ┌──────────────────────────────┐   │
│  │  packet_in handler           │   │
│  │    └─ classify()             │   │
│  │         └─ _build_match()    │   │
│  │         └─ _add_flow()       │   │
│  └──────────────────────────────┘   │
└──────────────┬──────────────────────┘
               │ OpenFlow 1.3 (TCP 6633)
┌──────────────▼──────────────────────┐
│   OVS Switch (s1)                   │
│  Flow table:                        │
│   prio=300 ip_proto=1  → queue0     │  ← CRITICAL (ICMP)
│   prio=200 tcp_dst=80  → queue1     │  ← HIGH (HTTP)
│   prio=100 tcp_dst=5001→ queue2     │  ← MEDIUM (iperf)
│   prio=50  (default)   → queue3     │  ← LOW (best-effort)
│                                     │
│  HTB Queues:                        │
│   queue0: 10 Mbps  queue1: 5 Mbps  │
│   queue2:  3 Mbps  queue3: 1 Mbps  │
└─────┬──────┬──────┬──────┬──────────┘
      │      │      │      │
     h1     h2     h3     h4
  10.0.0.1 .2    .3    .4
```

### Traffic Classification Table

| Class    | OF Priority | Queue | Port/Proto | Bandwidth |
|----------|-------------|-------|------------|-----------|
| CRITICAL | 300         | 0     | ICMP       | 10 Mbps   |
| HIGH     | 200         | 1     | TCP 22/53/80/443 | 5 Mbps |
| MEDIUM   | 100         | 2     | TCP 5001 (iperf) | 3 Mbps |
| LOW      | 50          | 3     | Everything else  | 1 Mbps |

---

## Repository Structure

```
.
├── qos_controller.py   # Ryu controller (main logic)
├── topology.py         # Mininet topology with queue configuration
├── test_validation.py  # Automated 2-scenario test suite
└── README.md
```

---

## Setup & Execution

### Prerequisites

```bash
# Ubuntu 20.04+ recommended
sudo apt-get update
sudo apt-get install -y mininet openvswitch-switch python3-pip wireshark iperf

pip3 install ryu eventlet==0.30.2
```

> **Note:** eventlet 0.30.2 is required for Ryu compatibility with Python 3.10+.

### Step 1 — Start the Ryu Controller

Open **Terminal 1**:

```bash
ryu-manager qos_controller.py --verbose
```

Expected output:
```
loading app qos_controller.py
instantiating app qos_controller.py
[HH:MM:SS.mmm] Switch 0000000000000001 connected – table-miss installed
```

### Step 2 — Start the Mininet Topology

Open **Terminal 2**:

```bash
sudo python3 topology.py
```

This starts the 4-host linear topology, configures OVS queues via OVSDB, and opens the Mininet CLI.

### Step 3 — Run Test Scenarios

**Option A — Automated test suite** (Terminal 3, topology must be running):

```bash
sudo python3 test_validation.py
```

**Option B — Manual CLI commands** (inside Mininet CLI):

```bash
# Scenario 1: ICMP (CRITICAL class)
mininet> h1 ping -c 5 h2

# Scenario 2: iperf HIGH class (port 80)
mininet> h2 iperf -s -p 80 &
mininet> h1 iperf -c 10.0.0.2 -p 80 -t 5

# Scenario 3: iperf LOW class (port 9999)
mininet> h4 iperf -s -p 9999 &
mininet> h3 iperf -c 10.0.0.4 -p 9999 -t 5

# View installed flow rules
mininet> s1 ovs-ofctl -O OpenFlow13 dump-flows s1

# View queue statistics
mininet> s1 ovs-ofctl -O OpenFlow13 dump-ports s1
```

---

## Test Scenarios & Expected Output

### Scenario 1 — Allowed vs Blocked (Latency under Load)

Tests that CRITICAL (ICMP) traffic maintains low RTT even when MEDIUM (iperf bulk) traffic saturates the link.

**Steps:**
```bash
# Terminal A: Start bulk flood (MEDIUM class)
h3 iperf -c 10.0.0.4 -p 5001 -u -b 80M -t 30 &

# Terminal B: Ping (CRITICAL class) – should stay low
h1 ping -c 10 -i 0.2 10.0.0.2
```

**Expected:**
- Baseline RTT: ~4–6 ms (2ms link × 2)
- Loaded RTT: <10 ms (degradation < 50%)
- Flow table shows `priority=300` ICMP rule and `priority=100` iperf rule

### Scenario 2 — Normal vs Failure (Throughput Comparison)

Compares throughput between HIGH priority port 80 and LOW priority port 9999 running concurrently.

**Steps:**
```bash
# Concurrent iperf flows
h2 iperf -s -p 80 &      # HIGH queue
h4 iperf -s -p 9999 &    # LOW queue
h1 iperf -c 10.0.0.2 -p 80   -t 10 &
h3 iperf -c 10.0.0.4 -p 9999 -t 10
```

**Expected:**
- Port 80 (HIGH): ≈ 5 Mbps (queue1 max-rate)
- Port 9999 (LOW): ≈ 1 Mbps (queue3 max-rate)
- Ratio ≥ 3×

---

## Proof of Execution

### Flow Table (after test scenarios)

```
OFPST_FLOW reply (OF1.3):
 cookie=0x0, duration=12.3s, table=0, n_packets=45, n_bytes=4410,
   idle_timeout=30, priority=300,icmp,in_port=1 actions=set_queue:0,output:2

 cookie=0x0, duration=8.1s,  table=0, n_packets=1820, n_bytes=2600480,
   idle_timeout=30, priority=100,tcp,in_port=3,tp_dst=5001 actions=set_queue:2,output:4

 cookie=0x0, duration=0s, table=0, n_packets=0, n_bytes=0,
   priority=0 actions=CONTROLLER:65535
```

### Ping Result (under load)

```
--- 10.0.0.2 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss
rtt min/avg/max/mdev = 4.1/5.3/7.2/0.8 ms
```

### iperf Comparison

```
HIGH (port 80)  : [  3]  0.0-5.0 sec  3.1 MBytes  5.2 Mbits/sec
LOW  (port 9999): [  3]  0.0-5.0 sec  0.6 MBytes  1.0 Mbits/sec
```

*Screenshots of Wireshark captures and terminal output can be added as images in this section.*

---

## SDN Concepts Demonstrated

| Concept | Where |
|---|---|
| Controller–switch interaction | `switch_features_handler` → table-miss flow |
| packet_in handling | `packet_in_handler` in `qos_controller.py` |
| match–action rule design | `_build_match()` + `_add_flow()` |
| Flow rule priorities | `PRIORITY_*` constants (50–300) |
| Idle timeouts | `FLOW_IDLE_TIMEOUT = 30s` |
| MAC learning | `self.mac_to_port` dict per datapath |
| QoS / queue scheduling | OVSDB HTB + `OFPActionSetQueue` |
| Multi-scenario validation | `test_validation.py` |

---

## References

1. Ryu SDN Framework Documentation — https://ryu.readthedocs.io/
2. OpenFlow 1.3 Specification — https://opennetworking.org/wp-content/uploads/2014/10/openflow-spec-v1.3.0.pdf
3. Mininet Walkthrough — http://mininet.org/walkthrough/
4. Open vSwitch OVSDB Guide — https://docs.openvswitch.org/en/latest/ref/ovsdb.7/
5. Ryu QoS Sample App — https://ryu.readthedocs.io/en/latest/app/ofctl_rest.html
6. "SDN: Software Defined Networks" — Nadeau & Gray, O'Reilly 2013

---

*Project submitted individually. All code written and tested by the student.*
