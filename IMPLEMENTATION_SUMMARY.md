# Testing Guide Improvement - Implementation Summary

## Overview

The testing methodology has been completely overhauled to support:

1. ✅ **Running tests 10 times with automatic averaging** - No manual repetition needed
2. ✅ **Collecting per-link load distribution data** - For heatmap visualization  
3. ✅ **Measuring algorithm calculation time separately** - Shows pure algorithm overhead vs transmission time
4. ✅ **Exporting all data to CSV** - Ready for user's plotting code

---

## What Was Changed

### 1. **base_controller.py** - Core Timing & Tracking

#### Added Data Structures:
```python
self.algorithm_times = {}          # (src_mac, dst_mac) -> calculation_time_ms
self.link_traffic = defaultdict(int)  # (src_dpid, dst_dpid, out_port) -> bytes
```

#### Added Methods:
```python
def record_algorithm_time(src_mac, dst_mac, calculation_time_ms)
    # Records algorithm execution time for export
    
def _packet_in_handler()  # MODIFIED
    # Now wraps compute_path() with timing measurement
    # Records time before and after path computation
    
def _reinstall_all_known_routes()  # MODIFIED  
    # Also wraps compute_path() with timing
    # For topology-change induced recomputation
```

**How it works:**
- When a packet arrives without a matching flow, controller computes path
- Time measurement wraps the `compute_path()` call: `time_after - time_before`
- Timing stored in MetricsCollector for CSV export
- This captures pure algorithm execution time (not including packet transmission)

### 2. **metrics.py** - Data Collection & Export

#### Added Data Structures:
```python
self.algorithm_times = {}  # (src_mac, dst_mac) -> calculation_time_ms
self.link_traffic = defaultdict(int)  # (src_dpid, dst_dpid, out_port) -> bytes
self.run_metrics = []  # List of metrics dicts from each run
```

#### Added Methods for Algorithm Timing:
```python
def record_algorithm_time(src_mac, dst_mac, calculation_time_ms)
    # Store timing from controller
    
def get_algorithm_time(src_mac, dst_mac)
    # Retrieve recorded time
    
def save_algorithm_times_to_csv()
    # Export to: algo_times_<algo>_<timestamp>.csv
```

#### Added Methods for Link Traffic:
```python
def record_link_traffic(src_dpid, dst_dpid, out_port, byte_count)
    # Accumulate bytes on each link
    
def get_link_traffic_summary()
    # Get all link statistics
    
def reset_link_traffic()
    # Clear counters for next run
    
def save_link_traffic_to_csv(run_number)
    # Export to: link_traffic_<algo>_<timestamp>.csv
```

#### Added Method for Multi-Run Support:
```python
def save_multi_run_summary(filename)
    # Calculate and export averages across all runs
    # Exports to: multi_run_summary_<algo>_<timestamp>.csv
```

### 3. **Multipath Controllers** - No Changes Needed!

The following controllers already benefit from the above modifications:
- `bfs_multipath_osken_controller.py` ✅
- `dijkstra_multipath_osken_controller.py` ✅
- `astar_multipath_osken_controller.py` ✅

They inherit all timing and tracking functionality from their parent classes.

### 4. **New Test Runner** - `test_runner_multi_run.py`

A complete standalone test automation script with:

**Features:**
- Runs tests N times (configurable, default 10)
- Tests all host pairs per iteration
- Measures: ping latency + iperf3 throughput
- Supports multiple topologies: diamond, clos
- Calculates: averages, min, max, standard deviation
- Exports 2 CSV files per run:
  - `metrics_<algo>_<timestamp>.csv` - All raw measurements
  - `statistics_<algo>_<timestamp>.csv` - Calculated statistics

**Usage:**
```bash
python3 SPF/test_runner_multi_run.py \
  --algorithm bfs \
  --topology diamond \
  --runs 10
```

### 5. **New Documentation** - `TESTING_GUIDE.md`

Comprehensive 400+ line guide covering:
- Testing architecture and data flow
- Quick start instructions (3-terminal setup)
- Output file specifications with examples
- Data analysis techniques:
  - Latency/throughput plotting
  - Algorithm timing comparison
  - Link utilization heatmaps
- Troubleshooting guide
- Implementation details
- Validation checklist

---

## Data Output Specification

All data is exported to `metrics/` directory. Five CSV files per test suite:

### 1. Raw Metrics (`metrics_<algo>_<timestamp>.csv`)

```csv
iteration,timestamp,src_host,dst_host,latency_ms,throughput_mbps
1,2026-06-06T12:34:56.789123,h1,h2,5.23,8.45
1,2026-06-06T12:34:58.123456,h2,h1,5.15,8.32
2,2026-06-06T12:35:10.456789,h1,h2,5.18,8.51
...
```

Contains all raw measurements from each iteration for each host pair.

### 2. Statistics Summary (`statistics_<algo>_<timestamp>.csv`)

```csv
flow,num_samples,avg_latency_ms,min_latency_ms,max_latency_ms,std_latency_ms,avg_throughput_mbps,...
h1->h2,10,5.20,5.12,5.31,0.05,8.48,8.32,8.61,0.08
h2->h1,10,5.19,5.11,5.28,0.04,8.42,8.25,8.55,0.09
```

Contains calculated statistics: averages with standard deviation, min/max values.

### 3. Algorithm Timing (`algo_times_<algo>_<timestamp>.csv`)

```csv
src_mac,dst_mac,calculation_time_ms,algorithm,multipath_enabled
00:00:00:00:00:01,00:00:00:00:00:02,2.345,bfs,True
00:00:00:00:00:02,00:00:00:00:00:01,2.321,bfs,True
```

Shows pure algorithm execution time in milliseconds:
- First packet triggers computation (~2-5 ms)
- Subsequent packets use cached paths
- Useful for comparing algorithm overhead

### 4. Per-Link Traffic (`link_traffic_<algo>_<timestamp>.csv`)

```csv
run_number,src_switch,dst_switch,out_port,total_bytes,algorithm,multipath_enabled
1,s1,s2,2,1024000,bfs,True
1,s1,s3,3,1024100,bfs,True
1,s2,s4,2,1024050,bfs,True
1,s3,s4,3,1023950,bfs,True
2,s1,s2,2,1024200,bfs,True
...
```

Shows traffic distribution across links:
- Can detect load balance success (equal traffic on equal-cost paths)
- Can generate heatmap visualization
- Shows link utilization

---

## How to Use

### Setup (3 Terminal Windows)

**Terminal 1 - Topology:**
```bash
cd /workspaces/learn_sdn
python3 SPF/topo-k3/topo-k3-diamond.py
# Or: python3 SPF/topo-k3/topo-k3-clos.py
```

**Terminal 2 - Controller:**
```bash
cd /workspaces/learn_sdn
python3 SPF/bfs_multipath_osken_controller.py
# Or: python3 SPF/dijkstra_multipath_osken_controller.py
# Or: python3 SPF/astar_multipath_osken_controller.py
```

**Terminal 3 - Test Runner:**
```bash
cd /workspaces/learn_sdn
python3 SPF/test_runner_multi_run.py \
  --algorithm bfs \
  --topology diamond \
  --runs 10
```

The test runner will automatically:
1. Run 10 iterations
2. Measure all host pairs in each iteration
3. Collect timing and traffic data
4. Save results to `metrics/` directory

---

## Key Improvements Over Previous Approach

| Aspect | Before | After |
|--------|--------|-------|
| **Test Runs** | Manual, 1 run | Automated, 10 runs |
| **Data Averaging** | Manual calculation | Automatic with statistics |
| **Algorithm Timing** | Not measured | Automatically captured in CSV |
| **Load Distribution** | Unknown | Exported per-link in CSV |
| **Data Export** | Partial/manual | Complete CSV suite |
| **Reproducibility** | Difficult | Fully automated |
| **Statistical Analysis** | Manual | Includes std dev, min/max |

---

## Example: Using the Exported Data for Plotting

Once you run the test suite, you can create analysis like:

### Latency Over Iterations
```python
import pandas as pd
df = pd.read_csv('metrics/metrics_bfs_diamond_*.csv')
df.groupby('iteration')['latency_ms'].mean().plot(kind='bar', title='Latency per Run')
```

### Throughput Comparison
```python
stats = pd.read_csv('metrics/statistics_bfs_diamond_*.csv')
stats.plot(x='flow', y=['avg_throughput_mbps', 'min_throughput_mbps', 'max_throughput_mbps'])
```

### Link Utilization Heatmap
```python
links = pd.read_csv('metrics/link_traffic_bfs_diamond_*.csv')
pivot = links.pivot_table(index='src_switch', columns='dst_switch', values='total_bytes')
import seaborn as sns
sns.heatmap(pivot, annot=True, fmt='g', cmap='YlOrRd')
```

### Algorithm Timing Comparison
```python
# Compare across algorithms
bfs_times = pd.read_csv('metrics/algo_times_bfs_*.csv')
dijkstra_times = pd.read_csv('metrics/algo_times_dijkstra_*.csv')
astar_times = pd.read_csv('metrics/algo_times_astar_*.csv')
# Calculate average timing per algorithm
```

---

## Files Modified

1. ✅ **SPF/base_controller.py** - Added timing & link tracking
2. ✅ **SPF/metrics.py** - Added export methods
3. ✅ **SPF/test_runner_multi_run.py** - NEW: Test automation script
4. ✅ **SPF/TESTING_GUIDE.md** - NEW: Comprehensive documentation

**Controllers (no changes needed):**
- SPF/bfs_multipath_osken_controller.py
- SPF/dijkstra_multipath_osken_controller.py
- SPF/astar_multipath_osken_controller.py

---

## Next Steps for User

1. **Review the new testing guide** - `SPF/TESTING_GUIDE.md`
2. **Run the test suite** using instructions above
3. **Create plotting code** to visualize exported CSV data
4. **Analyze results** to compare algorithm performance

The test runner and data collection infrastructure are now complete and ready to use!

