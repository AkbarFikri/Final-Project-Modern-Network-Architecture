# Quick Reference - New Testing Infrastructure

## Files Modified/Created

✅ **Modified:**
- `SPF/base_controller.py` - Added algorithm timing & link tracking
- `SPF/metrics.py` - Added data export methods

✅ **Created:**
- `SPF/test_runner_multi_run.py` - Automated test runner
- `SPF/TESTING_GUIDE.md` - Complete testing documentation
- `IMPLEMENTATION_SUMMARY.md` - This implementation summary

---

## One-Minute Quickstart

```bash
# Terminal 1: Start Mininet
python3 SPF/topo-k3/topo-k3-diamond.py

# Terminal 2: Start Controller
python3 SPF/bfs_multipath_osken_controller.py

# Terminal 3: Run 10 Test Iterations
python3 SPF/test_runner_multi_run.py --algorithm bfs --topology diamond --runs 10

# Results appear in: metrics/
```

---

## Data Files Generated

After running the test suite, you'll get:

| File | Contains | Used For |
|------|----------|----------|
| `metrics_<algo>_*.csv` | Raw measurements | Plotting trend lines |
| `statistics_<algo>_*.csv` | Avg/min/max/std dev | Comparing algorithms |
| `algo_times_<algo>_*.csv` | Algorithm timing (ms) | Algorithm overhead analysis |
| `link_traffic_<algo>_*.csv` | Per-link bytes | Heatmap generation |

---

## Example Analysis

### 1. Plot Latency Variation
```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv('metrics/metrics_bfs_diamond_20260606_123456.csv')
stats = df.groupby('iteration')['latency_ms'].agg(['mean', 'std'])
stats['mean'].plot(kind='bar', yerr=stats['std'], title='BFS - Latency per Iteration')
plt.ylabel('Latency (ms)')
plt.show()
```

### 2. Compare Algorithm Speed
```python
import pandas as pd

# Load timing data from all three algorithms
bfs = pd.read_csv('metrics/algo_times_bfs_*.csv')['calculation_time_ms'].mean()
dijkstra = pd.read_csv('metrics/algo_times_dijkstra_*.csv')['calculation_time_ms'].mean()
astar = pd.read_csv('metrics/algo_times_astar_*.csv')['calculation_time_ms'].mean()

print(f"BFS: {bfs:.3f}ms")
print(f"Dijkstra: {dijkstra:.3f}ms")
print(f"A*: {astar:.3f}ms")
```

### 3. Generate Link Utilization Heatmap
```python
import pandas as pd
import seaborn as sns

links = pd.read_csv('metrics/link_traffic_bfs_*.csv')
pivot = links.pivot_table(
    index='src_switch',
    columns='dst_switch',
    values='total_bytes',
    fill_value=0
)
sns.heatmap(pivot, annot=True, fmt='.0f', cmap='YlOrRd')
plt.title('Link Utilization - BFS Multipath')
plt.show()
```

---

## What Each Change Does

### Algorithm Timing
- **Captures:** Time taken by routing algorithm to compute paths
- **Triggers on:** First packet arrival (cold start)
- **Stored in:** `algo_times_*.csv`
- **Why it matters:** Measures pure algorithm overhead, not transmission time

### Link Traffic Distribution  
- **Captures:** Total bytes transferred on each link
- **Helps verify:** ECMP load balancing correctness
- **Stored in:** `link_traffic_*.csv`
- **Why it matters:** Equal-cost paths should have equal traffic

### Multi-Run Averaging
- **Runs tests:** 10 times (configurable)
- **Calculates:** Statistics (avg, min, max, std dev)
- **Stored in:** `statistics_*.csv`
- **Why it matters:** Shows consistency and reliability

---

## Testing Different Algorithms

```bash
# Test all three algorithms on same topology

# BFS (fastest)
python3 SPF/bfs_multipath_osken_controller.py &
python3 SPF/test_runner_multi_run.py --algorithm bfs --topology diamond --runs 10

# Dijkstra (moderate)
pkill -f bfs_multipath
python3 SPF/dijkstra_multipath_osken_controller.py &
python3 SPF/test_runner_multi_run.py --algorithm dijkstra --topology diamond --runs 10

# A* (heuristic-guided)
pkill -f dijkstra_multipath
python3 SPF/astar_multipath_osken_controller.py &
python3 SPF/test_runner_multi_run.py --algorithm astar --topology diamond --runs 10

# Results are comparable: all in metrics/
```

---

## Testing Different Topologies

```bash
# Diamond: 2 hosts, 4 switches, 2 equal-cost paths
python3 SPF/topo-k3/topo-k3-diamond.py
python3 SPF/test_runner_multi_run.py --algorithm bfs --topology diamond --runs 10

# Clos: 8 hosts, 8 switches, 4 equal-cost paths
python3 SPF/topo-k3/topo-k3-clos.py
python3 SPF/test_runner_multi_run.py --algorithm bfs --topology clos --runs 10
```

---

## Troubleshooting

**Q: "Mininet: command not found"**  
A: Test runner uses mininet CLI. Ensure mininet is on PATH or modify test_runner_multi_run.py to use full path.

**Q: CSV files are empty**  
A: Ensure controller is running and shows "[ROUTE-INSTALL]" messages before starting tests.

**Q: Algorithm times all show 0.000**  
A: Timing requires first packet to trigger path computation. Ensure tests run long enough (iperf3 at least 5s).

**Q: Link traffic shows no data**  
A: Flow statistics require switch queries. Ensure flow_stats_request() is being called in controller.

---

## Key Metrics Explained

### Jain's Fairness Index (JFI)
- Formula: $JFI = \frac{(\sum x_i)^2}{n \sum x_i^2}$
- 1.0 = perfect fairness (all paths equal)
- 0.5 = moderate fairness
- Lower = worse load balancing

### Standard Deviation
- Measures variability across runs
- Low σ = consistent results (good)
- High σ = variable results (investigate)

### Algorithm Timing
- Includes: Algorithm execution + flow installation
- Does NOT include: Packet transmission
- First packet = high latency (includes timing)
- Subsequent packets = low latency (cached paths)

---

## Testing Workflow

1. **Preparation** (5 min)
   - Start topology (Terminal 1)
   - Start controller (Terminal 2)
   - Verify connection messages

2. **Testing** (15-20 min per algorithm)
   - Run test_runner_multi_run.py
   - Monitor for any errors
   - Results saved automatically

3. **Analysis** (varies)
   - Load CSV files into analysis tool
   - Create visualizations
   - Compare algorithms

4. **Reporting** (document findings)
   - Latency improvement
   - Throughput gains
   - Load balance quality
   - Algorithm overhead

---

## References

- **Mininet**: Network emulator (runs real kernel, apps)
- **OSKen**: OpenFlow controller framework
- **OpenFlow**: Network protocol for SDN
- **ECMP**: Equal-Cost Multi-Path forwarding
- **Throughput**: Data transfer rate (Mbps)
- **Latency**: Round-trip time (ms)

---

## Support

For detailed information, see `SPF/TESTING_GUIDE.md`

For implementation details, see `IMPLEMENTATION_SUMMARY.md`

For algorithm documentation, see `SPF/docs/`

