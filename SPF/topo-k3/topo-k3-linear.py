#!/usr/bin/env python3
"""Linear topology for multipath SPF evaluation (K3 Group - Tugas Akhir).

Topology design: 2 switches with 2 hosts. Only one path available.
This serves as baseline (T1) to verify that all routing algorithms produce
identical results when no alternative paths exist.

ASCII art:

    h1          h2
     |          |
    (1)s1------s2(1)
        (2)  (2)
        
Link characteristics:
    s1-s2: 10 Mbps, 5ms delay (HFSC)

Use this topology to test:
    - Dijkstra single-path (should show 1 path)
    - ECMP (should show 1 path, as there's only 1 equal-cost path)
    - K-Path with K=2 (should show 1 path)
    
Expected behavior: All algorithms should produce identical results
since there is no multipath available.
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.link import TCLink
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel, info
from mininet.cli import CLI


class LinearTopo(Topo):
    """Simple linear topology with 2 switches and 2 hosts.
    
    Characteristics:
        - No multipath available (single path only)
        - Baseline for algorithm comparison
    """

    def addSwitch(self, name, **opts):
        kwargs = {"protocols": "OpenFlow13"}
        kwargs.update(opts)
        return super(LinearTopo, self).addSwitch(name, **kwargs)

    def __init__(self):
        Topo.__init__(self)

        info("*** Adding hosts\n")
        h1 = self.addHost("h1", ip="10.0.0.1/24")
        h2 = self.addHost("h2", ip="10.0.0.2/24")

        info("*** Adding switches\n")
        s1 = self.addSwitch("s1")
        s2 = self.addSwitch("s2")

        info("*** Adding host links\n")
        self.addLink(s1, h1, port1=1, port2=1)
        self.addLink(s2, h2, port1=1, port2=1)

        info("*** Adding switch links\n")
        self.addLink(s1, s2, port1=2, port2=2, bw=10, delay='5ms', use_hfsc=True)


def run():
    """Run the linear topology with Mininet."""
    topo = LinearTopo()
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
    CLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run()
