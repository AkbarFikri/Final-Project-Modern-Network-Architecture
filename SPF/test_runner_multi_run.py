#!/usr/bin/env python3
"""
Multi-run test runner for SPF multipath evaluation.

This script:
1. Runs performance tests multiple times (default: 10 runs)
2. Measures: latency (ping), throughput (iperf3), algorithm timing, per-link traffic
3. Collects data from each run independently
4. Exports: metrics to CSV, algorithm times, link distribution (for heatmaps), averages

Usage:
    python3 SPF/test_runner_multi_run.py --algorithm bfs --topology diamond --runs 10

The topology must already be running in another terminal:
    Terminal 1: python3 SPF/topo-k3/topo-k3-diamond.py
    Terminal 2: python3 SPF/bfs_multipath_osken_controller.py
    Terminal 3: python3 SPF/test_runner_multi_run.py --algorithm bfs --topology diamond

IMPORTANT: How to run this script:
    
    Option A (Recommended): Run from separate terminal while topology is running
    - Uses 'mnexec -a <pid>' to run commands inside Mininet host namespaces
    - Requires topology to be running (hosts h1, h2, etc. appear in 'ip netns list')
    - All metrics (ping, iperf3, algorithm timing, link traffic) will be collected
    
    Option B: Mininet not running
    - Latency/throughput measurements will be skipped
    - BUT: Controller will still collect algorithm timing and per-link traffic metrics

Output files are saved to metrics/ directory:
    - metrics_<algo>_<topo>_<timestamp>.csv     : Per-flow metrics from all runs
    - statistics_<algo>_<topo>_<timestamp>.csv  : Summary statistics with averages
"""

import argparse
import csv
import json
import logging
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def get_host_pid(host_name):
    """
    Get the PID of a Mininet host's shell process so we can attach to it
    with mnexec.

    Mininet marks each host's bash process with a title like 'mininet:h1',
    so we can find it via:  ps -eo pid,cmd | grep 'mininet:<host>'

    Args:
        host_name: e.g. 'h1'

    Returns:
        PID as string, or None if not found
    """
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,cmd"],
            capture_output=True, text=True, timeout=5
        )
        # Look for a line that contains 'mininet:h1' (exact host name)
        pattern = rf'^\s*(\d+)\s+.*mininet:{re.escape(host_name)}\b'
        match = re.search(pattern, result.stdout, re.MULTILINE)
        if match:
            return match.group(1)
    except Exception:
        pass

    # Fallback: try 'ip netns pids <host>' — returns PIDs in that namespace
    try:
        result = subprocess.run(
            ["ip", "netns", "pids", host_name],
            capture_output=True, text=True, timeout=5
        )
        pids = result.stdout.strip().split()
        if pids:
            return pids[0]  # return first PID (usually the bash shell)
    except Exception:
        pass

    return None


def get_host_ip(host_name):
    """
    Get IP address of a Mininet host by running 'ip addr' inside its
    namespace via mnexec.

    Falls back to Mininet's default IP scheme: 10.0.0.X for hX.

    Args:
        host_name: e.g. 'h1'

    Returns:
        IP address string, e.g. '10.0.0.1'
    """
    pid = get_host_pid(host_name)
    if pid:
        try:
            result = subprocess.run(
                ["mnexec", "-a", pid, "ip", "-4", "addr", "show"],
                capture_output=True, text=True, timeout=5
            )
            # Find all IPs, skip loopback (127.x.x.x)
            for match in re.finditer(r'inet\s+([\d.]+)/\d+', result.stdout):
                ip = match.group(1)
                if not ip.startswith("127."):
                    return ip
        except Exception:
            pass

    # Fallback: Mininet default is 10.0.0.X for hX
    num = re.sub(r'\D', '', host_name)
    if num:
        return f"10.0.0.{num}"

    return None


def host_available(host_name):
    """
    Check if a Mininet host is running by looking for its PID.

    Args:
        host_name: e.g. 'h1'

    Returns:
        True if host process found, False otherwise
    """
    return get_host_pid(host_name) is not None


class MultiRunTestRunner:
    """Runs performance tests multiple times and collects metrics."""

    def __init__(self, algorithm, topology, num_runs=10, output_dir="metrics"):
        """
        Initialize test runner.

        Args:
            algorithm: Routing algorithm (bfs, dijkstra, astar)
            topology: Topology name (diamond, clos)
            num_runs: Number of test runs
            output_dir: Directory for output files
        """
        self.algorithm = algorithm
        self.topology = topology
        self.num_runs = num_runs
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.all_runs_metrics = []
        self.all_algorithm_times = defaultdict(list)
        self.all_link_traffic = defaultdict(lambda: defaultdict(list))

        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        logger.info(f"Initialized test runner: algorithm={algorithm}, "
                    f"topology={topology}, runs={num_runs}")

    def get_mininet_hosts(self):
        """
        Get list of (src_host, dst_host) pairs to test.

        Returns:
            List of tuples (src_host_name, dst_host_name)
        """
        if self.topology == "diamond":
            return [("h1", "h2"), ("h2", "h1")]
        elif self.topology == "clos":
            return [
                ("h1", "h3"),
                ("h1", "h5"),
                ("h1", "h7"),
            ]
        else:
            raise ValueError(f"Unknown topology: {self.topology}")

    def run_ping(self, src_host, dst_host, count=5):
        """
        Measure latency using ping, executed inside the Mininet host's process
        via mnexec.

        Command: mnexec -a <pid_of_src> ping -c <count> <dst_ip>

        mnexec -a attaches to ALL namespaces of the target PID (network, mount,
        UTS, IPC) — identical to running from inside the Mininet host itself.

        Args:
            src_host: Source host name (e.g. 'h1')
            dst_host: Destination host name (e.g. 'h2')
            count: Number of ping packets

        Returns:
            Average RTT in ms, or None if failed
        """
        src_pid = get_host_pid(src_host)
        if not src_pid:
            logger.debug(f"  PID for '{src_host}' not found — is topology running?")
            return None

        dst_ip = get_host_ip(dst_host)
        if not dst_ip:
            logger.warning(f"  Could not determine IP for {dst_host}")
            return None

        try:
            cmd = ["mnexec", "-a", src_pid,
                   "ping", "-c", str(count), "-W", "2", dst_ip]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            # Parse: "min/avg/max/mdev = X/Y/Z/W ms"
            match = re.search(
                r'min/avg/max/(?:mdev|stddev)\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)',
                result.stdout
            )
            if match:
                avg_rtt = float(match.group(2))
                logger.info(f"  Ping {src_host} -> {dst_host} ({dst_ip}): {avg_rtt:.2f} ms")
                return round(avg_rtt, 2)
            else:
                logger.warning(f"  Ping {src_host} -> {dst_host}: no RTT in output")
                logger.debug(f"  stdout: {result.stdout.strip()}")
                logger.debug(f"  stderr: {result.stderr.strip()}")

        except subprocess.TimeoutExpired:
            logger.warning(f"  Ping {src_host} -> {dst_host}: timeout")
        except Exception as e:
            logger.warning(f"  Ping failed: {e}")

        return None

    def run_iperf(self, src_host, dst_host, duration=5, port=5201,
                  parallel=10, bandwidth_mbps=10):
        """
        Measure throughput using iperf3, executed inside Mininet host processes
        via mnexec.

        Uses parallel streams (-P) each capped at bandwidth_mbps/parallel Mbps (-b),
        totalling bandwidth_mbps — matching the max link capacity in the topology.

        Server: mnexec -a <dst_pid> iperf3 -s -p <port> --one-off
        Client: mnexec -a <src_pid> iperf3 -c <dst_ip> -p <port>
                       -t <dur> -P <parallel> -b <bw_per_stream>M -J

        Args:
            src_host:       Source host name (e.g. 'h1')
            dst_host:       Destination host name (e.g. 'h2')
            duration:       Test duration in seconds
            port:           iperf3 port
            parallel:       Number of parallel streams (default: 10)
            bandwidth_mbps: Total target bandwidth in Mbps (default: 10).
                            Divided equally across streams.

        Returns:
            Throughput in Mbps, or None if failed
        """
        src_pid = get_host_pid(src_host)
        dst_pid = get_host_pid(dst_host)

        if not src_pid or not dst_pid:
            logger.debug(f"  PID not found for {src_host} or {dst_host} — skipping iperf3")
            return None

        dst_ip = get_host_ip(dst_host)
        if not dst_ip:
            logger.warning(f"  Could not determine IP for {dst_host}")
            return None

        try:
            # Kill any leftover iperf3 server on dst
            subprocess.run(
                ["mnexec", "-a", dst_pid, "pkill", "-f", f"iperf3"],
                capture_output=True, timeout=3
            )
            time.sleep(0.5)

            # Start iperf3 server on destination (--one-off: exit after one client)
            logger.info(f"  Starting iperf3 server on {dst_host} (port {port})...")
            subprocess.Popen(
                ["mnexec", "-a", dst_pid,
                 "iperf3", "-s", "-p", str(port), "--one-off"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            time.sleep(1)  # Let server start

            # Run iperf3 client with parallel streams and bandwidth cap
            logger.info(f"  Running iperf3 {src_host} -> {dst_host} ({dst_ip}), "
                        f"{duration}s, {parallel} streams x {bandwidth_mbps:.1f} Mbps "
                        f"= {bandwidth_mbps} Mbps total...")
            cmd = ["mnexec", "-a", src_pid,
                   "iperf3", "-c", dst_ip, "-p", str(port),
                   "-t", str(duration),
                   "-P", str(parallel),
                   "-b", f"{bandwidth_mbps}M",
                   "-J"]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=duration + 15)

            # Parse JSON output
            try:
                # iperf3 -J outputs valid JSON directly
                data = json.loads(result.stdout)
                bits_per_sec = data['end']['sum_received']['bits_per_second']
                throughput = bits_per_sec / 1e6  # convert to Mbps
                logger.info(f"  Throughput {src_host} -> {dst_host}: {throughput:.2f} Mbps")
                return round(throughput, 2)
            except (json.JSONDecodeError, KeyError, TypeError):
                # Fallback: try text parsing
                match = re.search(r'([\d.]+)\s+Mbits/sec', result.stdout)
                if match:
                    throughput = float(match.group(1))
                    logger.info(f"  Throughput {src_host} -> {dst_host}: {throughput:.2f} Mbps")
                    return round(throughput, 2)
                logger.warning(f"  Could not parse iperf3 output")
                logger.debug(f"  stdout: {result.stdout[:300]}")
                logger.debug(f"  stderr: {result.stderr[:200]}")

        except subprocess.TimeoutExpired:
            logger.warning(f"  iperf3 timeout for {src_host} -> {dst_host}")
        except Exception as e:
            logger.warning(f"  iperf3 failed: {e}")
        finally:
            # Kill iperf3 server
            try:
                dst_pid = get_host_pid(dst_host)
                if dst_pid:
                    subprocess.run(
                        ["mnexec", "-a", dst_pid, "pkill", "-f", "iperf3"],
                        capture_output=True, timeout=3
                    )
            except Exception:
                pass

        return None

    def run_single_test_iteration(self, iteration):
        """
        Run a single test iteration (measure all host pairs).

        Args:
            iteration: Iteration number (1-based)

        Returns:
            Dict with metrics from this iteration
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"TEST ITERATION {iteration}/{self.num_runs}")
        logger.info(f"{'='*60}")

        iteration_metrics = {
            'iteration': iteration,
            'timestamp': datetime.now().isoformat(),
            'flows': []
        }

        host_pairs = self.get_mininet_hosts()
        namespaces_available = None  # determined on first attempt

        for src_host, dst_host in host_pairs:
            logger.info(f"\nMeasuring {src_host} -> {dst_host}...")

            flow_metrics = {
                'src_host': src_host,
                'dst_host': dst_host,
                'latency_ms': None,
                'throughput_mbps': None,
            }

            # Check host availability once
            if namespaces_available is None:
                namespaces_available = host_available(src_host)
                if not namespaces_available:
                    logger.info(f"  PID for '{src_host}' not found.")
                    logger.info("  Is the topology running? Check: ps aux | grep mininet")
                    logger.info("  Skipping latency/throughput — controller metrics still collected.")

            if namespaces_available:
                # Measure latency
                flow_metrics['latency_ms'] = self.run_ping(src_host, dst_host, count=4)
                time.sleep(1)

                # Measure throughput
                flow_metrics['throughput_mbps'] = self.run_iperf(src_host, dst_host, duration=5)
                time.sleep(2)
            else:
                logger.info(f"  Skipping ping & iperf3 (namespaces unavailable)")

            iteration_metrics['flows'].append(flow_metrics)

        logger.info(f"\nWaiting for controller metrics to be collected...")
        time.sleep(3)

        return iteration_metrics

    def run_all_iterations(self):
        """Run all test iterations."""
        logger.info(f"\n{'#'*60}")
        logger.info(f"# STARTING MULTI-RUN TEST SUITE")
        logger.info(f"# Algorithm: {self.algorithm}")
        logger.info(f"# Topology:  {self.topology}")
        logger.info(f"# Runs:      {self.num_runs}")
        logger.info(f"# Start:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'#'*60}")

        all_results = []

        for i in range(1, self.num_runs + 1):
            try:
                result = self.run_single_test_iteration(i)
                all_results.append(result)
                self.all_runs_metrics.append(result)

                if i < self.num_runs:
                    logger.info(f"\nWaiting before next iteration...")
                    time.sleep(5)

            except KeyboardInterrupt:
                logger.warning(f"Test interrupted by user at iteration {i}")
                break
            except Exception as e:
                logger.error(f"Error during iteration {i}: {e}")
                continue

        logger.info(f"\n{'#'*60}")
        logger.info(f"# COMPLETED {len(all_results)}/{self.num_runs} ITERATIONS")
        logger.info(f"# End: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'#'*60}\n")

        return all_results

    def calculate_statistics(self):
        """Calculate statistics across all iterations."""
        logger.info("\n" + "="*60)
        logger.info("CALCULATING STATISTICS")
        logger.info("="*60)

        stats = {
            'algorithm': self.algorithm,
            'topology': self.topology,
            'num_runs': len(self.all_runs_metrics),
            'flows': defaultdict(dict)
        }

        flow_data = defaultdict(lambda: {'latencies': [], 'throughputs': []})

        for run in self.all_runs_metrics:
            for flow in run['flows']:
                flow_key = f"{flow['src_host']}->{flow['dst_host']}"
                if flow['latency_ms'] is not None:
                    flow_data[flow_key]['latencies'].append(flow['latency_ms'])
                if flow['throughput_mbps'] is not None:
                    flow_data[flow_key]['throughputs'].append(flow['throughput_mbps'])

        for flow_key, values in flow_data.items():
            latencies = values['latencies']
            throughputs = values['throughputs']

            stats['flows'][flow_key] = {
                'avg_latency_ms':      sum(latencies) / len(latencies) if latencies else None,
                'min_latency_ms':      min(latencies) if latencies else None,
                'max_latency_ms':      max(latencies) if latencies else None,
                'std_latency_ms':      self._std_dev(latencies) if len(latencies) > 1 else None,
                'avg_throughput_mbps': sum(throughputs) / len(throughputs) if throughputs else None,
                'min_throughput_mbps': min(throughputs) if throughputs else None,
                'max_throughput_mbps': max(throughputs) if throughputs else None,
                'std_throughput_mbps': self._std_dev(throughputs) if len(throughputs) > 1 else None,
                'sample_count':        len(latencies) or len(throughputs)
            }

        return stats

    @staticmethod
    def _std_dev(values):
        if len(values) < 2:
            return None
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5

    def save_all_results(self, stats):
        logger.info("\n" + "="*60)
        logger.info("SAVING RESULTS TO CSV")
        logger.info("="*60)
        self._save_all_runs_csv()
        self._save_statistics_csv(stats)
        logger.info("="*60)

    def _save_all_runs_csv(self):
        filename = f"metrics_{self.algorithm}_{self.topology}_{self.timestamp}.csv"
        filepath = self.output_dir / filename

        fieldnames = ['iteration', 'timestamp', 'src_host', 'dst_host',
                      'latency_ms', 'throughput_mbps']

        try:
            with open(filepath, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for run in self.all_runs_metrics:
                    for flow in run['flows']:
                        writer.writerow({
                            'iteration':       run['iteration'],
                            'timestamp':       run['timestamp'],
                            'src_host':        flow['src_host'],
                            'dst_host':        flow['dst_host'],
                            'latency_ms':      flow['latency_ms'],
                            'throughput_mbps': flow['throughput_mbps'],
                        })
            logger.info(f"Saved: {filepath}")
        except Exception as e:
            logger.error(f"Failed to save metrics CSV: {e}")

    def _save_statistics_csv(self, stats):
        filename = f"statistics_{self.algorithm}_{self.topology}_{self.timestamp}.csv"
        filepath = self.output_dir / filename

        fieldnames = ['flow', 'num_samples',
                      'avg_latency_ms', 'min_latency_ms', 'max_latency_ms', 'std_latency_ms',
                      'avg_throughput_mbps', 'min_throughput_mbps', 'max_throughput_mbps',
                      'std_throughput_mbps']

        def fmt(v):
            return f"{v:.2f}" if v is not None else ''

        try:
            with open(filepath, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for flow_key, v in stats['flows'].items():
                    writer.writerow({
                        'flow':                  flow_key,
                        'num_samples':           v['sample_count'],
                        'avg_latency_ms':        fmt(v['avg_latency_ms']),
                        'min_latency_ms':        fmt(v['min_latency_ms']),
                        'max_latency_ms':        fmt(v['max_latency_ms']),
                        'std_latency_ms':        fmt(v['std_latency_ms']),
                        'avg_throughput_mbps':   fmt(v['avg_throughput_mbps']),
                        'min_throughput_mbps':   fmt(v['min_throughput_mbps']),
                        'max_throughput_mbps':   fmt(v['max_throughput_mbps']),
                        'std_throughput_mbps':   fmt(v['std_throughput_mbps']),
                    })
            logger.info(f"Saved: {filepath}")
        except Exception as e:
            logger.error(f"Failed to save statistics CSV: {e}")

    def print_summary(self, stats):
        logger.info("\n" + "="*80)
        logger.info(f"TEST SUMMARY - {self.algorithm.upper()} on {self.topology.upper()}")
        logger.info("="*80)
        logger.info(f"Completed iterations: {stats['num_runs']}/{self.num_runs}")
        logger.info(f"Output directory: {self.output_dir.absolute()}")

        for flow_key, v in stats['flows'].items():
            logger.info(f"\nFlow: {flow_key}")
            if v['avg_latency_ms'] is not None:
                std = v['std_latency_ms'] or 0
                logger.info(f"  Latency:    {v['avg_latency_ms']:.2f} ± {std:.2f} ms "
                            f"(min={v['min_latency_ms']:.2f}, max={v['max_latency_ms']:.2f})")
            else:
                logger.info("  Latency:    N/A")
            if v['avg_throughput_mbps'] is not None:
                std = v['std_throughput_mbps'] or 0
                logger.info(f"  Throughput: {v['avg_throughput_mbps']:.2f} ± {std:.2f} Mbps "
                            f"(min={v['min_throughput_mbps']:.2f}, max={v['max_throughput_mbps']:.2f})")
            else:
                logger.info("  Throughput: N/A")
            logger.info(f"  Samples:    {v['sample_count']}")

        logger.info("\n" + "="*80 + "\n")

    def run(self):
        """Main entry point: run all tests and save results."""
        try:
            results = self.run_all_iterations()
            if not results:
                logger.error("No test results collected!")
                return False
            stats = self.calculate_statistics()
            self.save_all_results(stats)
            self.print_summary(stats)
            return True
        except KeyboardInterrupt:
            logger.warning("Test suite interrupted by user")
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    parser = argparse.ArgumentParser(
        description='Multi-run performance test suite for SPF multipath routing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python3 test_runner_multi_run.py --algorithm bfs --topology diamond --runs 10
  python3 test_runner_multi_run.py --algorithm dijkstra --topology clos --runs 5
  python3 test_runner_multi_run.py --algorithm astar --topology clos

Prerequisites (each in separate terminal):
  Terminal 1: sudo python3 SPF/topo-k3/topo-k3-<topology>.py
  Terminal 2: ryu-manager SPF/<algorithm>_multipath_osken_controller.py
  Terminal 3: sudo python3 SPF/test_runner_multi_run.py --algorithm <algo> --topology <topo>

Note: Run with sudo so mnexec can attach to host namespaces.
        '''
    )

    parser.add_argument('--algorithm', '-a', required=True,
                        choices=['bfs', 'dijkstra', 'astar'],
                        help='Routing algorithm to test')
    parser.add_argument('--topology', '-t', required=True,
                        choices=['diamond', 'clos'],
                        help='Topology to test on')
    parser.add_argument('--runs', '-r', type=int, default=10,
                        help='Number of test iterations (default: 10)')
    parser.add_argument('--output-dir', '-o', default='metrics',
                        help='Output directory for CSV files (default: metrics/)')

    args = parser.parse_args()

    runner = MultiRunTestRunner(
        algorithm=args.algorithm,
        topology=args.topology,
        num_runs=args.runs,
        output_dir=args.output_dir
    )

    success = runner.run()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()