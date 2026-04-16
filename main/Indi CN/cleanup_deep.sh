#!/bin/bash
echo "=== Deep Cleanup for Mininet and OVS ==="

# Standard Mininet cleanup
sudo mn -c 2>/dev/null

# Kill any lingering processes
sudo pkill -9 ryu-manager 2>/dev/null
sudo pkill -9 python3 2>/dev/null
sudo killall iperf 2>/dev/null

# Delete ALL OVS bridges and queues
sudo ovs-vsctl --all destroy QoS 2>/dev/null
sudo ovs-vsctl --all destroy Queue 2>/dev/null
for br in $(sudo ovs-vsctl list-br 2>/dev/null); do
    sudo ovs-vsctl del-br $br
done

# Remove Mininet-created network namespaces
for ns in $(ip netns list | grep -E '^(h|s)[0-9]+'); do
    sudo ip netns del $ns
done

# Delete any leftover veth pairs (both ends)
for iface in $(ip link show | grep -oP '(h[0-9]+|s[0-9]+)-[^:@]+'); do
    sudo ip link delete $iface 2>/dev/null
done

# Clear OVS database
sudo systemctl restart openvswitch-switch 2>/dev/null

echo "Cleanup complete. Reboot if issues persist."