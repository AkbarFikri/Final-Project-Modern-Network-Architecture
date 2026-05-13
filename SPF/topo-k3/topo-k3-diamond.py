#!/usr/bin/env python3
"""Diamond topology for multipath SPF evaluation (K3 Group - Tugas Akhir).

Topology design: 4 switches with 2 hosts, providing 2 equal-cost paths.
This serves as validation scenario (T2) to test ECMP and K-Path algorithms
on a topology with limited but equal-cost alternative paths.

Port mapping (clean layout for ECMP):

                         h1
                         |
                      (port 1)
                         |
                         s1
                      /  |  \
                  (p2)(internal)(p3)
                    /    |    \
                  s2     X      s3
                   |             |
                (p2)          (p2)
                   |             |
                   +---> s4 <----+
                      (p2)(p3)

Two equal-cost paths from s1 to s4:
Path 1 (top):    s1(p2) -> s2(p1,p2) -> s4(p2)  [2 hops]
Path 2 (bottom): s1(p3) -> s3(p1,p2) -> s4(p3)  [2 hops]

Link characteristics:
    All links: 10 Mbps, 5ms delay (HFSC)
    Total capacity: ~20 Mbps when both paths utilized

Use this topology to test:
    - Dijkstra single-path (should show 1 path)
    - ECMP (should show 2 paths, load balanced) 
    - K-Path with K=2 (should show 2 paths, load balanced)

Expected behavior: 
    - ECMP and K-Path should distribute traffic across 2 paths
    - Throughput should reach ~20 Mbps (10 Mbps per path)
    - No packet drops
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.link import TCLink
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel, info
from mininet.cli import CLI


class DiamondTopo(Topo):
    """Diamond topology with 4 switches and 2 hosts.
    
    Provides 2 equal-cost paths between hosts.
    
    Characteristics:
        - 2 disjoint paths available (top and bottom paths)
        - Both paths have identical cost (10 Mbps, 5ms)
        - Ideal for testing basic multipath capabilities
    """

    def addSwitch(self, name, **opts):
        kwargs = {"protocols": "OpenFlow13"}
        kwargs.update(opts)
        return super(DiamondTopo, self).addSwitch(name, **kwargs)

    def __init__(self):
        Topo.__init__(self)

        info("*** Adding hosts\n")
        h1 = self.addHost("h1", ip="10.0.0.1/24")
        h2 = self.addHost("h2", ip="10.0.0.2/24")

        info("*** Adding switches\n")
        s1 = self.addSwitch("s1")
        s2 = self.addSwitch("s2")
        s3 = self.addSwitch("s3")
        s4 = self.addSwitch("s4")

        info("*** Adding host links\n")
        self.addLink(s1, h1, port1=1, port2=1)
        self.addLink(s4, h2, port1=1, port2=1)

        info("*** Adding switch links (diamond pattern - clean port mapping)\n")
        # Top path: s1 -> s2 -> s4
        # s1 port 2 ↔ s2 port 1
        # s2 port 2 ↔ s4 port 2
        self.addLink(s1, s2, port1=2, port2=1, bw=10, delay='5ms', use_hfsc=True)
        self.addLink(s2, s4, port1=2, port2=2, bw=10, delay='5ms', use_hfsc=True)
        
        # Bottom path: s1 -> s3 -> s4
        # s1 port 3 ↔ s3 port 1
        # s3 port 2 ↔ s4 port 3
        self.addLink(s1, s3, port1=3, port2=1, bw=10, delay='5ms', use_hfsc=True)
        self.addLink(s3, s4, port1=2, port2=3, bw=10, delay='5ms', use_hfsc=True)


def run():
    """Run the diamond topology with Mininet."""
    topo = DiamondTopo()
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
    info("*** Two equal-cost paths available between h1 and h2.\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run()
