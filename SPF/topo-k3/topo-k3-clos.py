#!/usr/bin/env python3
"""Spine-Leaf Clos topology for multipath SPF evaluation (K3 Group - Tugas Akhir).

Topology design: 4 spine switches, 4 leaf switches, 8 hosts (k=4).
This serves as the real-scale scenario (T3) representing modern data center
architecture with multiple equal-cost paths across spine-leaf fabric.

Switch naming: s1-s4 = spines, s5-s8 = leafs (consistent with other topologies)
Host IP: Flat /24 subnet (10.0.0.0/24) for simple inter-leaf routing via ECMP
Inter-leaf traffic: Automatically routed through controller (multipath ECMP)

Host allocation:
    - h1-h2 connected to leaf s5
    - h3-h4 connected to leaf s6
    - h5-h6 connected to leaf s7
    - h7-h8 connected to leaf s8
    All with IPs: 10.0.0.1/24 through 10.0.0.8/24


ASCII art (simplified):

    h1  h2      h3  h4      h5  h6      h7  h8
     |  |        |  |        |  |        |  |
    (1)(2)      (1)(2)      (1)(2)      (1)(2)
    s5          s6          s7          s8
     |  |        |  |        |  |        |  |
    (3)(4)(5)(6) (3)(4)(5)(6) (3)(4)(5)(6) (3)(4)(5)(6)
     \  |  |  /   \  |  |  /   \  |  |  /   \  |  |  /
      \ | | /     \ | | /     \ | | /     \ | | /
      +--+--+-----+--+--+-----+--+--+-----+--+--+
       s1  s2  s3  s4
      (1)(2)(3)(4) (1)(2)(3)(4) (1)(2)(3)(4) (1)(2)(3)(4)

Connectivity:
    - Spine switches: s1, s2, s3, s4 (aggregation layer)
    - Leaf switches: s5, s6, s7, s8 (access layer)
    - Each leaf is connected to all 4 spines
    - Each spine is connected to all 4 leafs
    - Provides k^2 = 16 equal-cost paths for multi-rack communication
    
Link characteristics:
    All inter-switch links: 10 Mbps, 5ms delay (HFSC)
    Host-to-leaf links: No bandwidth/delay constraints
    
Path analysis (e.g., h1@s5 to h3@s6):
    All paths go through exactly 3 hops (s5 -> spine -> s6)
    Number of equal-cost paths: 4 (one through each spine)
    Total aggregated capacity: ~40 Mbps

Use this topology to test:
    - Dijkstra single-path (should show 1 path)
    - ECMP (should show 4 paths, one through each spine)
    - K-Path with K=2 (should show 2 paths)

Expected behavior:
    - ECMP should distribute traffic across all 4 spines, achieving highest throughput
    - Demonstrates ECMP advantage on data center scale topologies
    - Represents real-world spine-leaf fabric used in cloud infrastructure
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.link import TCLink
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel, info
from mininet.cli import CLI


class ClosTopo(Topo):
    """Spine-Leaf Clos topology (k=4) with 8 switches, 8 hosts.
    
    Naming convention: s1-s4 = spine switches, s5-s8 = leaf switches.
    All hosts on flat 10.0.0.0/24 subnet for simple inter-leaf routing.
    Provides 4 equal-cost paths via different spines for inter-leaf communication.
    
    Characteristics:
        - 4 spine switches (s1-s4) in aggregation layer
        - 4 leaf switches (s5-s8) in access layer
        - 8 hosts (2 per leaf) on flat 10.0.0.0/24 subnet
        - Full mesh between leaves via spines (4 equal-cost paths)
        - Modern data center architecture pattern
        - All inter-leaf traffic routed via controller (multipath ECMP)
    """

    def addSwitch(self, name, **opts):
        kwargs = {"protocols": "OpenFlow13"}
        kwargs.update(opts)
        return super(ClosTopo, self).addSwitch(name, **kwargs)

    def __init__(self):
        Topo.__init__(self)

        info("*** Adding hosts\n")
        # Host distribution: 2 hosts per leaf (flat /24 subnet)
        h1 = self.addHost("h1", ip="10.0.0.1/24")
        h2 = self.addHost("h2", ip="10.0.0.2/24")
        h3 = self.addHost("h3", ip="10.0.0.3/24")
        h4 = self.addHost("h4", ip="10.0.0.4/24")
        h5 = self.addHost("h5", ip="10.0.0.5/24")
        h6 = self.addHost("h6", ip="10.0.0.6/24")
        h7 = self.addHost("h7", ip="10.0.0.7/24")
        h8 = self.addHost("h8", ip="10.0.0.8/24")

        info("*** Adding spine switches\n")
        s1 = self.addSwitch("s1")
        s2 = self.addSwitch("s2")
        s3 = self.addSwitch("s3")
        s4 = self.addSwitch("s4")

        info("*** Adding leaf switches\n")
        s5 = self.addSwitch("s5")
        s6 = self.addSwitch("s6")
        s7 = self.addSwitch("s7")
        s8 = self.addSwitch("s8")

        info("*** Adding host-to-leaf links\n")
        # Leaf s5
        self.addLink(s5, h1, port1=1, port2=1)
        self.addLink(s5, h2, port1=2, port2=1)
        # Leaf s6
        self.addLink(s6, h3, port1=1, port2=1)
        self.addLink(s6, h4, port1=2, port2=1)
        # Leaf s7
        self.addLink(s7, h5, port1=1, port2=1)
        self.addLink(s7, h6, port1=2, port2=1)
        # Leaf s8
        self.addLink(s8, h7, port1=1, port2=1)
        self.addLink(s8, h8, port1=2, port2=1)

        info("*** Adding spine-to-leaf links (full mesh)\n")
        # Leaf s5 to all spines
        self.addLink(s5, s1, port1=3, port2=1, bw=10, delay='5ms', use_hfsc=True)
        self.addLink(s5, s2, port1=4, port2=1, bw=10, delay='5ms', use_hfsc=True)
        self.addLink(s5, s3, port1=5, port2=1, bw=10, delay='5ms', use_hfsc=True)
        self.addLink(s5, s4, port1=6, port2=1, bw=10, delay='5ms', use_hfsc=True)

        # Leaf s6 to all spines
        self.addLink(s6, s1, port1=3, port2=2, bw=10, delay='5ms', use_hfsc=True)
        self.addLink(s6, s2, port1=4, port2=2, bw=10, delay='5ms', use_hfsc=True)
        self.addLink(s6, s3, port1=5, port2=2, bw=10, delay='5ms', use_hfsc=True)
        self.addLink(s6, s4, port1=6, port2=2, bw=10, delay='5ms', use_hfsc=True)

        # Leaf s7 to all spines
        self.addLink(s7, s1, port1=3, port2=3, bw=10, delay='5ms', use_hfsc=True)
        self.addLink(s7, s2, port1=4, port2=3, bw=10, delay='5ms', use_hfsc=True)
        self.addLink(s7, s3, port1=5, port2=3, bw=10, delay='5ms', use_hfsc=True)
        self.addLink(s7, s4, port1=6, port2=3, bw=10, delay='5ms', use_hfsc=True)

        # Leaf s8 to all spines
        self.addLink(s8, s1, port1=3, port2=4, bw=10, delay='5ms', use_hfsc=True)
        self.addLink(s8, s2, port1=4, port2=4, bw=10, delay='5ms', use_hfsc=True)
        self.addLink(s8, s3, port1=5, port2=4, bw=10, delay='5ms', use_hfsc=True)
        self.addLink(s8, s4, port1=6, port2=4, bw=10, delay='5ms', use_hfsc=True)


def run():
    """Run the Clos spine-leaf topology with Mininet."""
    topo = ClosTopo()
    net = Mininet(
        topo=topo,
        controller=RemoteController,
        link=TCLink,
        autoSetMacs=True,
        autoStaticArp=True,
        waitConnected=True,
    )

    info("\n*** Disabling IPv6\n")
    for host in net.hosts:
        info(f"disable ipv6 in {host}\n")
        host.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=1")

    for sw in net.switches:
        info(f"disable ipv6 in {sw}\n")
        sw.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=1")

    info("\n*** Starting network\n")
    net.start()

    info("*** Dumping host connections\n")
    dumpNodeConnections(net.hosts)
    info("\n*** Network is running. Type 'exit' to quit.\n")
    info("*** Clos spine-leaf topology with 4 equal-cost paths between leaves.\n")
    info("*** All hosts on flat 10.0.0.0/24 subnet.\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run()
