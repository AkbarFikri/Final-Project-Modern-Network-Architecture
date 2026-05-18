# SDN Metrics Collection Testing Guide

Complete step-by-step guide for collecting metrics data from different routing algorithms (BFS, Dijkstra, A*) in single-path and multipath modes.

## 📋 Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Setup](#setup)
4. [Test Procedures](#test-procedures)
5. [Data Collection](#data-collection)
6. [Post-Processing](#post-processing)
7. [Troubleshooting](#troubleshooting)

---

## Overview

This testing framework collects performance metrics for routing algorithms:

- **Algorithms**: BFS, Dijkstra, A*
- **Modes**: Single-path and Multipath (ECMP)
- **Metrics**: Throughput, Latency, Fairness Index, Active Paths
- **Tests**: 
  1. Concurrent iperf3 (no failures)
  2. Concurrent iperf3 with link failures
  3. Ping tests to multiple hosts
  4. Network traffic capture (tcpdump)

---

## Prerequisites

### Software Requirements

```bash
# Core dependencies
apt-get update
apt-get install -y mininet openvswitch-switch iperf3 iputils-ping tcpdump

# Python packages
pip install matplotlib pandas numpy openpyxl
```

### Directory Structure

```
/workspaces/learn_sdn/
├── SPF/
│   ├── *_osken_controller.py         # Controllers
│   ├── analyze_metrics.py            # Analysis script
│   ├── export_metrics.py             # Export script
│   └── topo-k3/
│       └── topo-k3-clos.py          # Clos topology
├── metrics/                          # CSV files (auto-generated)
│   └── metrics_*.csv
├── logs/                             # Test logs (to create)
│   ├── test_log_*.txt
│   ├── iperf3_*.log
│   ├── ping_*.log
│   └── tcpdump_*.pcap
└── plots/                            # Generated plots
    └── *.png
```

---

## Setup

### Create Directories

```bash
cd /workspaces/learn_sdn

# Create logging directories if they don't exist
mkdir -p logs
mkdir -p metrics
mkdir -p plots
```

### Terminal Setup

You'll need **4 terminal windows**:

1. **Terminal 1**: Controller
2. **Terminal 2**: Mininet topology
3. **Terminal 3**: Mininet CLI (for test commands)
4. **Terminal 4**: tcpdump (network capture)

---

## Test Procedures

### Test Suite Overview

| Test | Duration | Link State | Purpose |
|------|----------|-----------|---------|
| TEST-1 | 30s x 2 flows | Normal | Baseline throughput & fairness |
| TEST-2 | 30s x 2 flows | Link down at 10s | Resilience & failover |
| TEST-3 | 5 pings | Normal | Latency measurement |
| TEST-4 | 60s | Normal | Network capture |

---

## PART 1: TEST-1 - Concurrent iperf3 (No Link Failures)

### Step 1.1: Start Controller (Terminal 1)

```bash
cd /workspaces/learn_sdn

# Choose one algorithm and mode:

# Option A: Dijkstra Single-Path
python SPF/dijkstra_osken_controller.py

# Option B: Dijkstra Multipath (ECMP)
python SPF/dijkstra_multipath_osken_controller.py

# Option C: BFS Multipath
python SPF/bfs_multipath_osken_controller.py

# Option D: A* Multipath
python SPF/astar_multipath_osken_controller.py
```

**Expected Output:**
```
[01:05:04] [STATS-POLL] Started periodic polling (interval=5s)
[01:05:04] [METRICS] Enabled for dijkstra (multipath=True)
[TOPO-INITIAL] 8 switch(es) 32 link(s)
[TREE-DONE] root=s1 tree_edges=8 reachable=8/8
```

Wait for topology to stabilize (~10 seconds).

### Step 1.2: Start Topology (Terminal 2)

```bash
cd /workspaces/learn_sdn

python SPF/topo-k3/topo-k3-clos.py
```

**Expected Output:**
```
*** Creating network
*** Adding controller
*** Adding switches
...
*** Starting CLI:
mininet>
```

Wait for all hosts to be discovered. You should see:
```
[HOST-LEARN] MAC 00:00:00:00:00:01 discovered at s5 port 1
[HOST-LEARN] MAC 00:00:00:00:00:04 discovered at s6 port 2
...
```

### Step 1.3: Start tcpdump Capture (Terminal 4)

```bash
# Create tcpdump capture of all traffic
cd /workspaces/learn_sdn/logs

# Capture with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
sudo tcpdump -i any -w tcpdump_test1_${TIMESTAMP}.pcap -G 120 &

# Note: -G 120 rotates file every 120 seconds
```

### Step 1.4: Run iperf3 Test-1 (Terminal 3 - Mininet CLI)

```bash
# In mininet CLI, start iperf3 servers on destination hosts
mininet> h1 iperf3 -s -D -1 &
mininet> h4 iperf3 -s -D -1 &

# Wait 1-2 seconds for servers to start
mininet> sleep 2

# Run parallel iperf3 clients (10 parallel streams each for 30 seconds)
mininet> h6 iperf3 -b 10M -c h4 -p 5201 -t 30 -P 10 > ../logs/iperf3_test1_h6_to_h4.log &
mininet> h7 iperf3 -b 10M -c h1 -p 5201 -t 30 -P 10 > ../logs/iperf3_test1_h7_to_h1.log &

# Monitor progress
mininet> sleep 35
mininet> cat ../logs/iperf3_test1_h6_to_h4.log
mininet> cat ../logs/iperf3_test1_h7_to_h1.log
```

**Expected Output (iperf3 log):**
```
Connecting to host h4, port 5201
[  5] local 10.0.0.6 port 54210 connected to 10.0.0.4 port 5201
[  6] local 10.0.0.6 port 54211 connected to 10.0.0.4 port 5201
...
Interval           Transfer     Bitrate         Retr  Cwnd
0.00-2.00   sec  1.25 MBytes  5.25 Mbits/sec   0   1.37 MBytes
2.00-4.00   sec  1.38 MBytes  5.80 Mbits/sec   0   1.37 MBytes
...
- - - - - - - - - - - - - - - - - - - - - - - - -
[ ID] Interval           Transfer     Bitrate         Retr
[  5]   0.00-30.01  sec  93.1 MBytes  25.9 Mbits/sec   2
[  6]   0.00-30.01  sec  92.8 MBytes  25.8 Mbits/sec   1
...
Total send time: 30 sec
Total recv time: 30 sec
```

### Step 1.5: Stop Test-1 & Check Logs

```bash
mininet> pkill -f "iperf3 -s"
mininet> sleep 2

# Check metrics were saved
mininet> ls -lh ../logs/iperf3_test1_*.log
```

---

## PART 2: TEST-2 - Concurrent iperf3 with Link Failure

### Step 2.1: Restart Controller & Topology (Same as Step 1.1-1.2)

```bash
# Terminal 1: (Same controller as before, or restart for fresh run)

# Terminal 2:
python SPF/topo-k3/topo-k3-clos.py
```

Wait for topology to stabilize.

### Step 2.2: Identify Link to Fail

In mininet CLI, check link status:

```bash
mininet> net
```

Output will show links like:
```
s1-eth1<->s5-eth3
s1-eth2<->s2-eth3
s1-eth3<->s3-eth3
...
```

Choose a link to fail, e.g., `s3-eth1<->s8-eth2`

### Step 2.3: Run iperf3 Test-2 with Link Down (Terminal 3)

```bash
mininet> h1 iperf3 -s -D -1 &
mininet> h4 iperf3 -s -D -1 &
mininet> sleep 2

# Start iperf3 clients (same as TEST-1)
mininet> h6 iperf3 -b 10M -c h4 -p 5201 -t 30 -P 10 > ../logs/iperf3_test2_h6_to_h4.log &
mininet> h7 iperf3 -b 10M -c h1 -p 5201 -t 30 -P 10 > ../logs/iperf3_test2_h7_to_h1.log &

# Wait 10 seconds, then bring down a link
mininet> sleep 10

# Bring down link (run in separate command)
mininet> link s3 s8 down

# Log shows link down
# [TOPO-CHANGE] switches=8 links=31 delta +0 -1
# [TOPO-DOWN] [(8, 3)]
# [PATH-MP] ... recalculating routes ...

# Let test continue for remaining 20 seconds
mininet> sleep 20

# Bring link back up
mininet> link s3 s8 up

# [TOPO-UP] [(8, 3)]
# Routes recalculate again

# Wait for test to finish
mininet> sleep 5
```

### Step 2.4: Check Results

```bash
mininet> cat ../logs/iperf3_test2_h6_to_h4.log
mininet> cat ../logs/iperf3_test2_h7_to_h1.log
```

**Expected Behavior:**
- At 10s mark: throughput may dip (link down)
- At ~30-35s mark: throughput recovers (link up + reroute)
- Compare logs to verify failover response time

---

## PART 3: TEST-3 - Ping Tests

### Step 3.1: Run Ping Tests (Terminal 3)

```bash
# Ping from multiple hosts to verify latency
# 5 ping packets, save output

mininet> h1 ping -c 5 h4 > ../logs/ping_test_h1_to_h4.log
mininet> h6 ping -c 5 h7 > ../logs/ping_test_h6_to_h7.log
mininet> h4 ping -c 5 h1 > ../logs/ping_test_h4_to_h1.log
mininet> h7 ping -c 5 h6 > ../logs/ping_test_h7_to_h6.log

# Check results
mininet> cat ../logs/ping_test_*.log
```

**Expected Output (ping log):**
```
PING 10.0.0.4 (10.0.0.4) 56(84) bytes of data.
64 bytes from 10.0.0.4: icmp_seq=1 ttl=64 time=1.23 ms
64 bytes from 10.0.0.4: icmp_seq=2 ttl=64 time=1.15 ms
64 bytes from 10.0.0.4: icmp_seq=3 ttl=64 time=1.18 ms
64 bytes from 10.0.0.4: icmp_seq=4 ttl=64 time=1.21 ms
64 bytes from 10.0.0.4: icmp_seq=5 ttl=64 time=1.19 ms

--- 10.0.0.4 statistics ---
5 packets transmitted, 5 received, 0% packet loss, time 4002ms
rtt min/avg/max/mdev = 1.15/1.19/1.23/0.03 ms
```

---

## PART 4: Gather All Logs

### Step 4.1: Stop Controller (Terminal 1)

```bash
# Press Ctrl+C in controller terminal

# Output should show:
[SIGNAL] SIGINT received, initiating graceful shutdown...
[01:06:58] [CONTROLLER-STOP] clearing 4 hosts, 12 paths
[01:07:00] [STATS-POLL] Stopped periodic polling
[CSV] Metrics saved to metrics/metrics_dijkstra_20260518_010700.csv
[01:07:00] [METRICS] Saved 12 flows to CSV
[01:07:00] [CONTROLLER-EXIT] graceful exit complete
```

### Step 4.2: Stop Mininet (Terminal 2)

```bash
# In mininet CLI:
mininet> exit

# Or press Ctrl+C and confirm exit
```

### Step 4.3: Stop tcpdump (Terminal 4)

```bash
# Press Ctrl+C to stop tcpdump
# Or: sudo pkill tcpdump
```

### Step 4.4: Collect All Logs

```bash
cd /workspaces/learn_sdn

# Create test summary directory
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p test_results_${TIMESTAMP}

# Copy all results
cp metrics/metrics_*.csv test_results_${TIMESTAMP}/
cp logs/* test_results_${TIMESTAMP}/ 2>/dev/null
cp plots/*.png test_results_${TIMESTAMP}/ 2>/dev/null

# Create manifest
cat > test_results_${TIMESTAMP}/README.txt << 'EOF'
Test Results Summary
====================
Algorithm: [INSERT ALGORITHM NAME]
Mode: [INSERT SINGLE-PATH or MULTIPATH]
Test Date: [TIMESTAMP]

Files:
- metrics_*.csv: Metrics collected by controller
- iperf3_test1_*.log: Throughput test 1 (no failures)
- iperf3_test2_*.log: Throughput test 2 (with link failure)
- ping_test_*.log: Latency measurements
- tcpdump_*.pcap: Network packet capture

Analysis:
Run analyze_metrics.py to generate plots
EOF

# Verify collection
ls -lah test_results_${TIMESTAMP}/
```

---

## Data Collection

### Directory Layout After Tests

```
/workspaces/learn_sdn/
├── metrics/
│   ├── metrics_dijkstra_20260518_110000.csv     # Controller metrics
│   ├── metrics_dijkstra_20260518_120000.csv
│   └── metrics_dijkstra_20260518_130000.csv
├── logs/
│   ├── iperf3_test1_h6_to_h4.log               # Throughput logs
│   ├── iperf3_test1_h7_to_h1.log
│   ├── iperf3_test2_h6_to_h4.log               # With link failure
│   ├── iperf3_test2_h7_to_h1.log
│   ├── ping_test_h1_to_h4.log                  # Latency logs
│   ├── ping_test_h6_to_h7.log
│   ├── ping_test_h4_to_h1.log
│   ├── ping_test_h7_to_h6.log
│   ├── tcpdump_test1_20260518_110000.pcap      # Network captures
│   ├── tcpdump_test2_20260518_120000.pcap
│   └── tcpdump_test3_20260518_130000.pcap
└── test_results_20260518_140000/               # Final results
    ├── metrics_*.csv
    ├── iperf3_*.log
    ├── ping_*.log
    ├── tcpdump_*.pcap
    └── README.txt
```

---

## Post-Processing

### Extract Metrics from Logs

#### From iperf3 logs:

```bash
# Parse throughput (Mbps)
grep "bits_per_second" logs/iperf3_test1_h6_to_h4.log | tail -1

# Parse number of parallel connections
grep "^\[" logs/iperf3_test1_h6_to_h4.log | grep "connected" | wc -l

# Parse retransmissions
grep "Retr" logs/iperf3_test1_h6_to_h4.log | tail -5
```

#### From ping logs:

```bash
# Extract average RTT
grep "min/avg/max" logs/ping_test_h1_to_h4.log | awk '{print $4}' | cut -d'/' -f2

# Extract loss percentage
grep "received" logs/ping_test_h1_to_h4.log | awk '{print $6}'
```

#### From CSV metrics:

```bash
cd SPF/

# Analyze all metrics
python analyze_metrics.py ../metrics/

# Export to formats
python export_metrics.py ../metrics/ --format json --output ../results.json
python export_metrics.py ../metrics/ --format html --output ../report.html
python export_metrics.py ../metrics/ --format excel --output ../results.xlsx
```

### Process tcpdump Captures

```bash
# Convert to readable format
tcpdump -r logs/tcpdump_test1_*.pcap -A | head -100

# Filter specific protocol
tcpdump -r logs/tcpdump_test1_*.pcap "icmp or iperf" | wc -l

# Extract statistics
tcpdump -r logs/tcpdump_test1_*.pcap | grep "iperf" | wc -l
```

---

## Complete Testing Workflow (Automated Script)

Here's a helper script to automate the entire process:

```bash
#!/bin/bash
# run_complete_test.sh

set -e

ALGORITHM="${1:-dijkstra_multipath}"
TEST_NAME="test_${ALGORITHM}_$(date +%Y%m%d_%H%M%S)"
RESULTS_DIR="/workspaces/learn_sdn/test_results_${TEST_NAME}"

echo "[TEST] Starting complete test suite for ${ALGORITHM}"
mkdir -p "${RESULTS_DIR}"

# Cleanup old metrics
rm -f /workspaces/learn_sdn/metrics/metrics_*.csv

echo "[TEST] Step 1: Start controller..."
cd /workspaces/learn_sdn
python SPF/${ALGORITHM}_osken_controller.py &
CONTROLLER_PID=$!
sleep 5

echo "[TEST] Step 2: Start topology..."
python SPF/topo-k3/topo-k3-clos.py &
TOPO_PID=$!
sleep 10

echo "[TEST] Step 3: Run test suite..."
# (Run through mininet CLI - this requires manual interaction)
# Use screen or tmux for automation

echo "[TEST] Step 4: Collect results..."
cp metrics/metrics_*.csv "${RESULTS_DIR}/"
cp logs/* "${RESULTS_DIR}/" 2>/dev/null || true

echo "[TEST] Step 5: Cleanup..."
kill $CONTROLLER_PID $TOPO_PID

echo "[TEST] Complete! Results saved to ${RESULTS_DIR}/"
ls -la "${RESULTS_DIR}/"
```

Usage:
```bash
chmod +x run_complete_test.sh
./run_complete_test.sh dijkstra_multipath
```

---

## Comparison Across Algorithms

To collect data for all algorithms:

```bash
# Algorithm list
ALGORITHMS=(
    "bfs_osken_controller"
    "bfs_multipath_osken_controller"
    "dijkstra_osken_controller"
    "dijkstra_multipath_osken_controller"
    "astar_osken_controller"
    "astar_multipath_osken_controller"
)

# For each algorithm:
for algo in "${ALGORITHMS[@]}"; do
    echo "Testing ${algo}..."
    # Run test suite following Part 1-4 above
    # Collect metrics
done

# After all tests
python SPF/analyze_metrics.py metrics/ --output plots/
```

---

## Expected Results

### Single-Path Algorithm
```
Active Paths: 1
Jain's Fairness Index: 1.0 (single path, no distribution)
Throughput: ~10 Mbps (limited to one path)
Latency: ~1.2 ms
```

### Multipath Algorithm (ECMP)
```
Active Paths: 4 (Clos topology with K=3)
Jain's Fairness Index: 1.0 (equal distribution across 4 paths)
Throughput: ~10 Mbps x 4 = 40 Mbps potential
Latency: ~1.2 ms (same hop count as single-path)
```

### With Link Failure
```
Single-Path: Traffic loss during reroute (10-50ms)
Multipath: Continuous traffic on remaining paths (no loss)
```

---

## Troubleshooting

### Issue: Metrics not saved
```bash
# Check if controller actually enabled metrics
grep "\[METRICS\]" controller.log

# Verify flows were installed
grep "\[PATH-INSTALL\]" controller.log
```

### Issue: iperf3 connection refused
```bash
# Make sure servers are running
mininet> ps aux | grep iperf3

# Check port is not in use
mininet> netstat -an | grep 5201
```

### Issue: Link down command not working
```bash
# Must be exact switch names
mininet> net    # See all links
mininet> link s3 s8 down  # Must match s3-eth*<->s8-eth*
```

### Issue: tcpdump permission denied
```bash
# tcpdump requires sudo
sudo tcpdump -i any -w output.pcap &
```

### Issue: Logs directory not writable
```bash
# Create with proper permissions
sudo mkdir -p /workspaces/learn_sdn/logs
sudo chmod 777 /workspaces/learn_sdn/logs
```

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `python SPF/dijkstra_multipath_osken_controller.py` | Start controller |
| `python SPF/topo-k3/topo-k3-clos.py` | Start topology |
| `h1 iperf3 -s -D -1 &` | Start iperf3 server |
| `h6 iperf3 -c h4 -t 30 -P 10` | Run iperf3 with 10 streams |
| `h1 ping -c 5 h4` | Ping test (5 packets) |
| `link s1 s5 down` | Bring down link (mininet) |
| `python SPF/analyze_metrics.py metrics/` | Analyze metrics |
| `python SPF/export_metrics.py metrics/ --format html` | Generate HTML report |

---

## Next Steps

1. Run all tests for one algorithm
2. Collect metrics from CSV files
3. Run `analyze_metrics.py` to generate plots
4. Export to HTML for visualization
5. Repeat for other algorithms
6. Compare results across algorithms

---

**Last Updated**: May 18, 2026
**Author**: SDN Learning Project
