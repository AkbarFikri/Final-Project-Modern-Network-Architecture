"""BFS SPF OpenFlow controller.

Single-source shortest path forwarding using Breadth-First Search.
BFS is the simplest possible unweighted shortest-path algorithm and serves
as the baseline for teaching: it guarantees minimum hop count because it
explores nodes level by level, ensuring the first time a node is reached
it is via the shortest path.

Complexity:   O(V + E) — linear in graph size (optimal for unweighted graphs)
Metric:       hop count (all edges weight 1)
Multipath:    no - single best path per (src, dst)
ECMP:         no

When to use BFS vs Dijkstra:
    BFS:      unweighted graphs, simplest implementation, O(V+E) optimal
    Dijkstra: weighted graphs, O((V+E) log V), degrades to BFS when weights=1
    A*:       like Dijkstra + heuristic, faster with a good h(v), single-target

Run:
    python3 bfs_osken_controller.py
    python3 bfs_osken_controller.py --verbose

See Also:
    dijkstra_osken_controller.py - generalizes BFS to weighted graphs
    astar_osken_controller.py    - adds heuristic to prune the search
"""

import os
import sys

from base_controller import SPFBaseController
from algorithms.bfs import bfs

BFS_FLOW_COOKIE = 0x4246530000000001     # "BFS\0" in hex
BFS_FLOW_COOKIE_MASK = 0xFFFFFFFFFFFFFFFF
BFS_FLOW_PRIORITY = 100


class BFSSwitch(SPFBaseController):
    """Single shortest-path forwarding using Breadth-First Search.

    The simplest possible minimum-hop-count router.  BFS explores all
    neighbours at the current hop-distance before moving to the next,
    so the first time any node is reached it is guaranteed to be on a
    shortest path.

    Teaching note — BFS vs Dijkstra on an unweighted graph:
        BFS uses a plain deque (FIFO): cost to reach level k is always k.
        Dijkstra uses a min-heap: generalises to arbitrary positive weights.
        On hop-count topologies they return the same distances; BFS is faster
        because it avoids heap operations.
    """

    FLOW_COOKIE = BFS_FLOW_COOKIE

    def __init__(self, *args, **kwargs):
        super(BFSSwitch, self).__init__(*args, **kwargs)
        # Enable metrics collection for BFS single-path
        if not self.metrics_enabled:
            self.enable_metrics(algorithm_name="bfs", multipath=False, output_dir="metrics")

    def compute_path(self, src, dst, first_port, final_port):
        """Compute shortest hop-count path using BFS.

        Algorithm steps:
            1. BFS from src, level by level (queue-based, not heap)
            2. Stop as soon as dst is dequeued (guaranteed shortest path)
            3. Reconstruct path by following predecessor pointers back to src
        """
        self.logger.debug("[PATH-QUERY] BFS: s%d -> s%d", src, dst)

        # --- Phase 1: BFS from src ---
        # distance[v] = hop count from src; previous[v] = predecessor
        # BFS visits each node exactly once, in non-decreasing hop order.
        distance, previous = bfs(self.adjacency, src)

        reachable = sum(1 for d in distance.values() if d != float("inf"))
        self.logger.info("[SPF-DONE] BFS s%d->s%d reachable=%d/%d",
                         src, dst, reachable, len(distance))

        # --- Phase 2: Reconstruct path from predecessor pointers ---
        return self._reconstruct_path(src, dst, first_port, final_port, distance, previous)


if __name__ == '__main__':
    current_file = os.path.abspath(__file__)
    passthrough_args = sys.argv[1:]
    if '--observe-links' not in passthrough_args:
        passthrough_args = ['--observe-links'] + passthrough_args
    sys.argv = ['bfs_osken_controller', *passthrough_args, current_file]
    from os_ken.cmd.manager import main
    sys.exit(main())
