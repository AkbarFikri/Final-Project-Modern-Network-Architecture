# SPF Multipath Testing Guide

## Overview

This guide describes the improved testing methodology for evaluating shortest-path forwarding (SPF) algorithms with multipath ECMP support. The testing framework now:

1. ✅ Runs tests **10 times** and **averages** results (not just once)
2. ✅ Collects **per-link traffic distribution** data for heatmap visualization
3. ✅ Measures **algorithm calculation time** separately from packet transmission time
4. ✅ Exports all data in **CSV format** for further analysis and plotting

---

## Test Architecture

### Data Collection Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Mininet Topology (topo-k3-diamond.py or topo-k3-clos.py)   │
│                                                              │
│  Controllers instrumented with timing & traffic tracking:   │
│  - BFS Multipath Controller                                 │
│  - Dijkstra Multipath Controller                            │
│  - A* Multipath Controller                                  │
└─────────────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────────────┐
│ Test Runner (test_runner_multi_run.py)                      │
│                                                              │
│ For each of 10 iterations:                                  │
│  1. Measure ping latency (RTT)                              │
│  2. Measure iperf3 throughput                               │
│  3. Collect algorithm calculation times                     │
│  4. Collect per-link traffic statistics                     │
└─────────────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────────────┐
│ Output CSV Files (metrics/ directory)                       │
│                                                              │
│  - metrics_<algo>_<timestamp>.csv                           │
│  - statistics_<algo>_<timestamp>.csv                        │
│  - algo_times_<algo>_<timestamp>.csv                        │
│  - link_traffic_<algo>_<timestamp>.csv                      │
└─────────────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────────────┐
│ User's Plotting Code (matplotlib/seaborn)                   │
│                                                              │
│  Plot generation for:                                       │
│  - Latency comparison across runs                           │
│  - Throughput comparison                                    │
│  - Algorithm calculation time per algorithm                 │
│  - Link utilization heatmaps                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Required Modifications

### 1. Controller Modifications

The following modifications have been made to support data collection:

#### base_controller.py

- **Algorithm Timing**: `compute_path()` calls are wrapped with timing measurement
  - Timing is recorded for both:
    - Initial path computation on first packet (triggers controller processing)
    - Subsequent path recomputation (after topology changes)
  - Uses `record_algorithm_time()` to store times in MetricsCollector

- **Per-Link Tracking**: Infrastructure added to track link usage
  - `install_path()` now records which links are being used
  - Link traffic is accumulated in `link_traffic` dictionary

#### metrics.py

New methods added to MetricsCollector:

- `record_algorithm_time(src_mac, dst_mac, calculation_time_ms)` - Store algorithm timing
- `record_link_traffic(src_dpid, dst_dpid, out_port, byte_count)` - Track per-link bytes
- `get_algorithm_time(src_mac, dst_mac)` - Retrieve recorded times
- `get_link_traffic_summary()` - Get link traffic breakdown
- `reset_link_traffic()` - Clear counters for multi-run averaging
- `save_algorithm_times_to_csv()` - Export algorithm times
- `save_link_traffic_to_csv(run_number)` - Export per-link distribution
- `save_multi_run_summary(filename)` - Export averaged metrics

### 2. Multipath Controllers

No changes needed! The following controllers automatically benefit from the above modifications:

- `bfs_multipath_osken_controller.py`
- `dijkstra_multipath_osken_controller.py`
- `astar_multipath_osken_controller.py`

They inherit all timing and tracking infrastructure from their parent classes.

---

## Quick Start

### Prerequisites

Ensure the following are available:
- Mininet with OpenFlow support
- OSKen (OpenFlow controller framework)
- iperf3 installed on all hosts
- Python 3.8+

### Step 1: Start Mininet Topology (Terminal 1)

```bash
# For diamond topology (simple: 2 hosts, 4 switches, 2 equal-cost paths)
cd /workspaces/learn_sdn
python3 SPF/topo-k3/topo-k3-diamond.py

# OR for Clos topology (advanced: 8 hosts, 8 switches, 4 equal-cost paths)
# python3 SPF/topo-k3/topo-k3-clos.py
```

Output should show:
```
*** Disabling IPv6
*** Starting network
*** Dumping host connections
*** Network is running. Type 'exit' to quit.
```

Do NOT exit Mininet - keep it running!

### Step 2: Start Controller (Terminal 2)

```bash
cd /workspaces/learn_sdn

# For BFS multipath
python3 SPF/bfs_multipath_osken_controller.py

# For Dijkstra multipath
# python3 SPF/dijkstra_multipath_osken_controller.py

# For A* multipath
# python3 SPF/astar_multipath_osken_controller.py
```

Wait until you see connection messages like:
```
[TOPO-DONE] ...
[TREE-DONE] ...
[ROUTE-INSTALL] ...
```

Do NOT exit the controller - keep it running!

### Step 3: Run Test Suite (Terminal 3)

```bash
cd /workspaces/learn_sdn

# Run 10 iterations of tests
python3 SPF/test_runner_multi_run.py \
  --algorithm bfs \
  --topology diamond \
  --runs 10

# Alternative: test Dijkstra or A*
# python3 SPF/test_runner_multi_run.py --algorithm dijkstra --topology diamond --runs 10
# python3 SPF/test_runner_multi_run.py --algorithm astar --topology clos --runs 10
```

The test runner will:
1. Run 10 iterations of performance tests
2. For each iteration, measure all host pairs
3. For each host pair:
   - Ping 4 packets (measure latency)
   - Run iperf3 for 5 seconds (measure throughput)
4. Save all results to CSV files in `metrics/` directory

---

## Output Data

### File Structure

All output files are saved to the `metrics/` directory:

```
metrics/
├── metrics_bfs_diamond_20260606_123456.csv
│   └── Raw measurements from all 10 runs
│       Columns: iteration, timestamp, src_host, dst_host, latency_ms, throughput_mbps
│
├── statistics_bfs_diamond_20260606_123456.csv
│   └── Calculated statistics with averages
│       Columns: flow, num_samples, avg_latency_ms, min_latency_ms, max_latency_ms, 
│                std_latency_ms, avg_throughput_mbps, ...
│
├── algo_times_bfs_20260606_123456.csv
│   └── Algorithm calculation times (milliseconds)
│       Columns: src_mac, dst_mac, calculation_time_ms, algorithm, multipath_enabled
│
└── link_traffic_bfs_20260606_123456.csv
    └── Per-link traffic distribution (bytes transferred)
        Columns: run_number, src_switch, dst_switch, out_port, total_bytes, 
                 algorithm, multipath_enabled
```

### Example Output: metrics_bfs_diamond_*.csv

```csv
iteration,timestamp,src_host,dst_host,latency_ms,throughput_mbps
1,2026-06-06T12:34:56.789123,h1,h2,5.23,8.45
1,2026-06-06T12:34:58.123456,h2,h1,5.15,8.32
2,2026-06-06T12:35:10.456789,h1,h2,5.18,8.51
2,2026-06-06T12:35:12.123456,h2,h1,5.21,8.38
...
```

### Example Output: algo_times_bfs_*.csv

```csv
src_mac,dst_mac,calculation_time_ms,algorithm,multipath_enabled
00:00:00:00:00:01,00:00:00:00:00:02,2.345,bfs,True
00:00:00:00:00:02,00:00:00:00:00:01,2.321,bfs,True
...
```

**Interpretation:**
- The first packet triggers algorithm execution (~2.3 ms for BFS on diamond topology)
- Subsequent packets use cached paths (fast)
- This timing can be used to estimate:
  - Pure algorithm computation time
  - Overhead of controller path installation
  - Total latency impact of SDN routing decisions

### Example Output: link_traffic_bfs_*.csv

```csv
run_number,src_switch,out_port,dst_switch,total_bytes,algorithm,multipath_enabled
1,s1,2,s2,1024000,bfs,True
1,s1,3,s3,1024000,bfs,True
1,s2,2,s4,1024000,bfs,True
1,s3,3,s4,1024000,bfs,True
2,s1,2,s2,1024100,bfs,True
...
```

**Interpretation:**
- Shows which links carry traffic (non-zero bytes)
- Link identified by: (src_switch, out_port, dst_switch)
- Shows relative load on each link
- For ECMP: equal-cost paths should have similar byte counts
- For heatmap: bytes/port indicates link utilization
- Actual data comes from OpenFlow switch flow statistics

---

## Data Analysis & Plotting

### 1. Latency & Throughput Analysis

The `metrics_*.csv` files contain raw measurements for creating:

```python
import pandas as pd
import matplotlib.pyplot as plt

# Read results
df = pd.read_csv('metrics_bfs_diamond_20260606_123456.csv')

# Plot 1: Latency distribution across runs
df.groupby('iteration')['latency_ms'].mean().plot(kind='bar')
plt.ylabel('Latency (ms)')
plt.xlabel('Iteration')
plt.title('BFS Multipath - Latency per Iteration')

# Plot 2: Throughput distribution across runs
df.groupby('iteration')['throughput_mbps'].mean().plot(kind='bar')
plt.ylabel('Throughput (Mbps)')
plt.xlabel('Iteration')
plt.title('BFS Multipath - Throughput per Iteration')

# Plot 3: Per-flow averages
stats_df = pd.read_csv('statistics_bfs_diamond_20260606_123456.csv')
stats_df.set_index('flow')[['avg_latency_ms', 'avg_throughput_mbps']].plot()
```

### 2. Algorithm Calculation Time Analysis

The `algo_times_*.csv` file shows:

```python
# Read algorithm times
algo_df = pd.read_csv('algo_times_bfs_20260606_123456.csv')

# Compare across algorithms
import seaborn as sns
# (after combining data from all three algorithms)
sns.boxplot(data=combined_df, x='algorithm', y='calculation_time_ms')
plt.title('Algorithm Calculation Time Comparison')
plt.ylabel('Time (ms)')
```

**Key insights:**
- BFS: fastest (O(V+E) complexity)
- Dijkstra: moderate (O((V+E)log V) complexity)
- A*: may be faster due to heuristic pruning

### 3. Load Distribution (Heatmap)

The `link_traffic_*.csv` file can be used for:

```python
import pandas as pd
import numpy as np
import seaborn as sns

# Read link traffic data
links_df = pd.read_csv('metrics/link_traffic_bfs_20260606_123456.csv')

# Create a pivot table where:
# - Rows: source switches
# - Columns: destination switches
# - Values: total bytes transferred

# First, aggregate all rows with the same (src, dst) pair
link_agg = links_df.groupby(['src_switch', 'dst_switch'])['total_bytes'].sum().reset_index()

# Pivot into matrix form
pivot_data = link_agg.pivot(index='src_switch', columns='dst_switch', values='total_bytes')
pivot_data = pivot_data.fillna(0)

# Plot heatmap
plt.figure(figsize=(8, 6))
sns.heatmap(pivot_data, annot=True, fmt='.0f', cmap='YlOrRd', cbar_kws={'label': 'Bytes'})
plt.title(f'BFS Multipath - Link Utilization Heatmap')
plt.ylabel('Source Switch')
plt.xlabel('Destination Switch')
plt.tight_layout()
plt.show()
```

**For multipath algorithms:**
- Equal-cost paths should show similar traffic distribution
- Unequal traffic may indicate:
  - Implementation issues
  - Round-robin not working correctly
  - Different path costs than expected

---

## Advanced Usage

### Custom Test Scenarios

To test different host pairs or topologies, modify test_runner_multi_run.py:

```python
# In get_mininet_hosts() method, customize:
def get_mininet_hosts(self):
    if self.topology == "diamond":
        return [("h1", "h2"), ("h2", "h1")]  # Edit this
    elif self.topology == "clos":
        return [
            ("h1", "h3"),   # Edit these
            ("h1", "h5"),
            ("h1", "h7"),
        ]
```

### Longer Test Durations

To test with longer iperf3 durations (capture more data):

```bash
# Modify in test_runner_multi_run.py:
# Line with: flow_metrics['throughput_mbps'] = self.run_iperf(..., duration=5)
# Change to: flow_metrics['throughput_mbps'] = self.run_iperf(..., duration=30)
```

### Testing with Different Controllers

```bash
# Test each algorithm separately:

# BFS (fastest, basic)
python3 SPF/bfs_multipath_osken_controller.py &
sleep 2
python3 SPF/test_runner_multi_run.py --algorithm bfs --topology diamond --runs 10
pkill -f bfs_multipath

# Dijkstra (moderate complexity)
python3 SPF/dijkstra_multipath_osken_controller.py &
sleep 2
python3 SPF/test_runner_multi_run.py --algorithm dijkstra --topology diamond --runs 10
pkill -f dijkstra_multipath

# A* (heuristic guided)
python3 SPF/astar_multipath_osken_controller.py &
sleep 2
python3 SPF/test_runner_multi_run.py --algorithm astar --topology diamond --runs 10
pkill -f astar_multipath
```

---

## Troubleshooting

### Issue: "Mininet: command not found"

The test runner uses Mininet CLI to invoke commands on hosts. Ensure Mininet is properly installed:

```bash
# Check if Mininet is available
which mininet

# If not, install it
sudo apt-get install mininet
```

### Issue: iperf3 fails with "permission denied"

Ensure iperf3 is installed inside Mininet hosts:

```bash
# In Mininet CLI:
mininet> h1 apt-get install -y iperf3
mininet> h2 apt-get install -y iperf3
```

### Issue: "No route to host"

Check that the controller is running and switches are connected:

```bash
# In Terminal 2 (controller), look for:
# [TOPO-DONE] ... 
# [ROUTE-INSTALL] ...

# If not appearing, the topology and controller may not be connected
# Restart both
```

### Issue: CSV files empty or missing data

This can happen if:

1. **Controller didn't record metrics**: Ensure `--enable-metrics` or similar flag is used
   
2. **Tests ran too fast**: Algorithm timing only triggers on first packet. Subsequent packets use cached paths.
   - Solution: Clear controller state between runs or restart controller

3. **Link traffic not tracked**: Link statistics come from switch statistics polling
   - Ensure `request_flow_stats()` is being called in base_controller.py

---

## Implementation Details

### Algorithm Timing Measurement

**How it works:**
1. When a new flow arrives (PacketIn event), the controller calls `compute_path()`
2. Timing is wrapped around this call: `time_before = time.time()` ... `time_after = time.time()`
3. Calculation time = (time_after - time_before) * 1000 milliseconds
4. Recorded via `record_algorithm_time(src_mac, dst_mac, calc_time_ms)`
5. Also stored in MetricsCollector for export to CSV

**Why separate from packet transmission time:**
- First packet is SLOW: Controller must compute path (2-5ms) + install flows + forward packet
- Subsequent packets are FAST: Flows already installed, hardware forwarding (sub-1ms)
- Ping shows total latency including algorithm computation
- CSV `algo_times_*.csv` shows pure algorithm time

### Per-Link Traffic Tracking

**How it works:**
1. Flows are installed on switches with specific paths
2. Switches report flow statistics via OpenFlow (OFPFlowStatsReply)
3. Flow statistics include: (eth_src, eth_dst) -> (packet_count, byte_count)
4. Controller receives these stats and correlates them to installed paths
5. For each flow, the controller determines which links it uses
6. Bytes are accumulated per link: (src_dpid, out_port, dst_dpid)
7. For multipath algorithms:
   - Multiple flows may use the same link
   - Load should be distributed across equal-cost paths
   - Jain's Fairness Index measures distribution quality

**Data extraction process:**
- Controller maintains: `installed_paths[(src_mac, dst_mac)] -> path list`
- When switch reports bytes for a flow on switch X:
  - Find which hop in path is on switch X
  - Identify output port and next-hop switch
  - Accumulate bytes to: `link_traffic[(X, out_port, next_hop)]`
- Metrics collector extracts `link_traffic` from controller
- Exported to CSV with actual bytes transferred per link

### Multi-Run Averaging

**Methodology:**
1. Run tests 10 times independently
2. Each run measures all host pairs multiple times
3. Average metrics are calculated across all runs
4. Standard deviation shows consistency/variability
5. This gives statistical confidence in results

**Why 10 runs?**
- Captures normal variation in network performance
- Provides sufficient samples for statistical analysis
- Takes ~15-20 minutes depending on iperf3 duration
- Balances statistical rigor vs. test duration

---

## Validation Checklist

Before considering tests complete:

- [ ] Completed 10 iterations without errors
- [ ] CSV files generated and contain data
- [ ] Latency values are reasonable (1-20ms for local mininet)
- [ ] Throughput values are reasonable (5-10 Mbps for 10Mbps links)
- [ ] Algorithm times recorded (1-5ms for basic algorithms)
- [ ] Link traffic shows data for expected paths
- [ ] For ECMP: multiple paths have similar byte counts
- [ ] For single-path: only one link per flow has traffic

---

## Next Steps

After collecting data:

1. **Run the provided plotting scripts** (to be created by user)
   - Latency vs iteration graphs
   - Throughput comparison charts
   - Algorithm timing histograms
   - Link utilization heatmaps

2. **Compare algorithms:**
   - Which is fastest? (latency)
   - Which is most reliable? (std dev)
   - Which distributes load best? (heatmap)
   - Which uses least CPU? (algorithm timing)

3. **Validate ECMP correctness:**
   - Equal-cost paths should have equal traffic (for multipath)
   - Single-path algorithms should show one active path per flow
   - Jain's Fairness Index should be close to 1.0 for good load balance

---

## References

- **Jain's Fairness Index**: (sum x_i)² / (n * sum x_i²) where x_i is flow i's throughput
  - 1.0 = perfectly fair
  - 0.5 = moderately fair
  - Lower values indicate poor load balancing

- **Standard Deviation**: Measure of variability across runs
  - Low std = consistent results
  - High std = high variance (potential issues)

- **Mininet**: Network emulator - runs real kernel, switches, applications
  - Each host is a Linux namespace
  - Switches are OpenFlow-enabled
  - Ideal for testing network algorithms

- **OSKen**: OpenFlow controller framework
  - Pure Python implementation
  - Simple to instrument with measurements
  - Used for all SPF controllers in this lab

---

## Questions?

If encountering issues:

1. Check controller logs for error messages
2. Verify Mininet topology is running: `mininet> nodes`
3. Test basic connectivity: `mininet> h1 ping -c 2 h2`
4. Ensure iperf3 is available: `mininet> h1 which iperf3`
5. Check output directory exists: `ls -la metrics/`

