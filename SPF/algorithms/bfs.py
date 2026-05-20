"""Breadth-First Search shortest path algorithm.

BFS finds the shortest path (minimum hop count) in an *unweighted* graph.
It explores nodes level by level, guaranteeing the first time a node is
reached its distance is optimal.

Complexity:  O(V + E)  time,  O(V)  space
Use when:    All edges have equal cost (hop-count routing).
Limitation:  Cannot handle weighted edges.

Comparison with Dijkstra:
    BFS uses a FIFO queue.  All edge weights are implicitly 1.
    Dijkstra uses a min-heap.  Edges may have different non-negative weights.
    On unweighted graphs BFS is faster in practice (no heap overhead).
"""

from collections import deque, defaultdict


def bfs(adjacency, src, weights=None):
    """Shortest path via BFS (unweighted).

    Args:
        adjacency: dict  {node: [(neighbor, out_port), ...]}
        weights:   ignored — BFS always uses unit edge costs.

    Returns:
        (distance, previous)
        distance[v] = minimum hop count from src to v  (inf if unreachable)
        previous[v] = predecessor of v on the shortest path from src
    """
    # --- Phase 1: Initialise distances for every known vertex ---
    # Collect all vertices reachable from the adjacency structure.
    distance = {}
    previous = {}
    for node in adjacency:
        distance[node] = float("inf")
        previous[node] = None
        for neighbor, _ in adjacency[node]:
            distance.setdefault(neighbor, float("inf"))
            previous.setdefault(neighbor, None)

    if src not in distance:
        return distance, previous

    # --- Phase 2: BFS from source ---
    # Enqueue src with distance 0.
    distance[src] = 0
    queue = deque([src])

    while queue:
        u = queue.popleft()                         # O(1) dequeue

        for v, _ in adjacency.get(u, []):           # examine all neighbours
            if distance[v] == float("inf"):         # v not yet visited?
                distance[v] = distance[u] + 1      # every hop costs 1
                previous[v] = u
                queue.append(v)                     # enqueue for later expansion

    return distance, previous


def bfs_multi_parent(adjacency, src, weights=None):
    """BFS variant that keeps ALL equal-cost predecessors per node.

    Used by multipath controllers to enumerate all equal-cost paths for
    ECMP load balancing. Since BFS explores nodes level by level, any
    predecessor found at the same distance is an equal-cost path.

    Args:
        adjacency: dict  {node: [(neighbor, out_port), ...]}
        weights:   ignored — BFS always uses unit edge costs.

    Returns:
        (distance, parents)
        distance[v] = minimum hop count from src to v  (inf if unreachable)
        parents[v]  = set of nodes u where dist[u] + 1 == dist[v]
    """
    # --- Phase 1: Initialise distances for every known vertex ---
    distance = {}
    parents = defaultdict(set)

    for node in adjacency:
        distance[node] = float("inf")
        for neighbor, _ in adjacency[node]:
            distance.setdefault(neighbor, float("inf"))

    if src not in distance:
        return distance, parents

    # --- Phase 2: BFS from source, collecting all equal-cost parents ---
    distance[src] = 0
    queue = deque([src])
    visited = {src}

    while queue:
        u = queue.popleft()

        for v, _ in adjacency.get(u, []):
            alt = distance[u] + 1

            if alt < distance[v]:
                # Strictly better path found — replace parent set
                distance[v] = alt
                parents[v] = {u}
                if v not in visited:
                    queue.append(v)
                    visited.add(v)
            elif alt == distance[v] and u not in parents[v]:
                # Equal-cost path found — add to parent set
                parents[v].add(u)

    return distance, parents
