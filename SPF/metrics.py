"""
Metrics collection module for SDN performance measurement.

Measures:
    1. Throughput Aggregate (iperf3): Total Mbps from source to destination
    2. End-to-End Latency (ping): Average RTT in milliseconds
    3. Load Balance Index (Jain's Fairness Index): 0=uneven, 1=perfect
    4. Active Paths: Number of paths actually carrying traffic

Statistics are collected directly from OpenFlow switches via polling,
not from controller, to capture real traffic distribution.
"""

import csv
import subprocess
import time
import logging
import os
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path


class MetricsCollector:
    """Collects performance metrics for SDN flows."""

    def __init__(self, controller, output_dir="metrics", algorithm_name="unknown"):
        """
        Initialize metrics collector.

        Args:
            controller: SPFBaseController instance (for switch access)
            output_dir: Directory to save CSV files
            algorithm_name: Name of routing algorithm (bfs, dijkstra, astar, etc.)
        """
        self.controller = controller
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.algorithm = algorithm_name
        self.logger = logging.getLogger(__name__)
        self.multipath_enabled = False
        
        # Metrics storage: (src_mac, dst_mac) -> metrics_dict
        self.flow_metrics = defaultdict(dict)
        
        # Flow statistics cache: (switch_dpid, flow_id) -> (packet_count, byte_count)
        self.flow_stats_cache = {}
        
        # Algorithm timing: (src_mac, dst_mac) -> calculation_time_ms
        self.algorithm_times = {}
        
        # Per-link traffic: (src_dpid, dst_dpid, out_port) -> bytes
        self.link_traffic = defaultdict(int)
        
        # Multi-run support: List to accumulate metrics across runs
        self.run_metrics = []  # List of metric dictionaries from each run
        
        # Timestamp for duration calculation
        self.start_time = time.time()

    def set_multipath_enabled(self, enabled):
        """Set whether multipath forwarding is enabled."""
        self.multipath_enabled = enabled
    
    def record_algorithm_time(self, src_mac, dst_mac, calculation_time_ms):
        """Record algorithm calculation time for a flow.
        
        Args:
            src_mac: Source MAC address
            dst_mac: Destination MAC address
            calculation_time_ms: Time in milliseconds
        """
        key = (src_mac, dst_mac)
        self.algorithm_times[key] = calculation_time_ms
        self.logger.debug(f"[ALGO-TIME] {src_mac} -> {dst_mac}: {calculation_time_ms:.3f} ms")
    
    def get_algorithm_time(self, src_mac, dst_mac):
        """Get recorded algorithm time for a flow."""
        key = (src_mac, dst_mac)
        return self.algorithm_times.get(key, 0.0)
    
    def record_link_traffic(self, src_dpid, dst_dpid, out_port, byte_count):
        """Record traffic on a specific link.
        
        Args:
            src_dpid: Source switch DPID
            dst_dpid: Destination switch DPID
            out_port: Outgoing port number on src_dpid
            byte_count: Number of bytes transferred
        """
        link_key = (src_dpid, dst_dpid, out_port)
        self.link_traffic[link_key] += byte_count
        self.logger.debug(f"[LINK-TRAFFIC] s{src_dpid} -> s{dst_dpid} (port {out_port}): {byte_count} bytes")
    
    def get_link_traffic_summary(self):
        """Get summary of per-link traffic from controller.
        
        Returns:
            Dict of {(src_dpid, out_port, dst_dpid): total_bytes}
        """
        if not self.controller:
            return {}
        
        # Get link traffic directly from controller
        return dict(self.controller.link_traffic) if hasattr(self.controller, 'link_traffic') else {}
    
    def reset_link_traffic(self):
        """Reset per-link traffic counters in controller."""
        if self.controller and hasattr(self.controller, 'link_traffic'):
            self.controller.link_traffic.clear()
            self.logger.info("[LINK-RESET] Per-link traffic counters cleared")
    
    def save_run_metrics(self, metrics_dict, run_number=None):
        """Save metrics from a single test run.
        
        Args:
            metrics_dict: Metrics from one run
            run_number: Run number for tracking
        """
        if run_number is not None:
            metrics_dict['run_number'] = run_number
        self.run_metrics.append(metrics_dict)

    # ──────────────────────────────────────────────────────────────────────────
    # 1. THROUGHPUT MEASUREMENT (iperf3)
    # ──────────────────────────────────────────────────────────────────────────

    def measure_throughput(self, src_host, dst_host, duration=10, port=5201):
        """
        Measure throughput between two hosts using iperf3.

        Args:
            src_host: Source host object (from Mininet)
            dst_host: Destination host object (from Mininet)
            duration: Test duration in seconds
            port: iperf3 port (default 5201)

        Returns:
            Throughput in Mbps (float), or None if measurement failed
        """
        try:
            self.logger.info(f"[THROUGHPUT] Starting iperf3 {src_host.name} -> {dst_host.name}")
            
            # Start iperf3 server on destination
            dst_host.cmd(f"iperf3 -s -p {port} -D > /dev/null 2>&1")
            time.sleep(0.5)  # Allow server to start
            
            # Run iperf3 client on source
            cmd = f"iperf3 -c {dst_host.IP()} -p {port} -t {duration} -J"
            result = src_host.cmd(cmd)
            
            # Parse JSON output
            try:
                # Extract JSON from output (iperf3 -J outputs JSON)
                json_match = re.search(r'\{.*\}', result, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    throughput_mbps = data['end']['sum_received']['bits_per_second'] / 1e6
                    self.logger.info(f"[THROUGHPUT-RESULT] {throughput_mbps:.2f} Mbps")
                    return round(throughput_mbps, 2)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                self.logger.warning(f"[THROUGHPUT-PARSE] JSON parsing failed: {e}")
                # Fallback: parse text output
                return self._parse_iperf3_text(result)
            
        except Exception as e:
            self.logger.error(f"[THROUGHPUT-ERROR] {e}")
            return None
        finally:
            # Kill iperf3 server
            dst_host.cmd(f"pkill -f 'iperf3 -s -p {port}'")

    def _parse_iperf3_text(self, output):
        """Fallback parser for iperf3 text output."""
        try:
            # Look for "bits_per_second" line
            match = re.search(r'(\d+\.?\d*)\s+Mbps', output)
            if match:
                return float(match.group(1))
            
            # Alternative: look for "MBytes" and "seconds"
            bytes_match = re.search(r'(\d+\.?\d*)\s+MBytes', output)
            time_match = re.search(r'(\d+\.?\d*)\s+sec', output)
            if bytes_match and time_match:
                mbytes = float(bytes_match.group(1))
                seconds = float(time_match.group(1))
                mbps = (mbytes * 8) / seconds
                return round(mbps, 2)
        except Exception as e:
            self.logger.warning(f"[IPERF3-PARSE] Text fallback failed: {e}")
        
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # 2. LATENCY MEASUREMENT (ping)
    # ──────────────────────────────────────────────────────────────────────────

    def measure_latency(self, src_host, dst_host, count=5):
        """
        Measure RTT latency between two hosts using ping.

        Args:
            src_host: Source host object (from Mininet)
            dst_host: Destination host object (from Mininet)
            count: Number of ping packets to send

        Returns:
            Average RTT in milliseconds (float), or None if measurement failed
        """
        try:
            self.logger.info(f"[LATENCY] Pinging {src_host.name} -> {dst_host.name}")
            
            dst_ip = dst_host.IP()
            cmd = f"ping -c {count} {dst_ip}"
            result = src_host.cmd(cmd)
            
            # Parse ping output: "min/avg/max/stddev = X/Y/Z/W ms"
            match = re.search(r'min/avg/max/(?:stddev|mdev)\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', result)
            if match:
                avg_rtt = float(match.group(2))
                self.logger.info(f"[LATENCY-RESULT] {avg_rtt:.2f} ms")
                return round(avg_rtt, 2)
            else:
                self.logger.warning(f"[LATENCY-PARSE] Could not parse ping output")
                return None
                
        except Exception as e:
            self.logger.error(f"[LATENCY-ERROR] {e}")
            return None

    # ──────────────────────────────────────────────────────────────────────────
    # 3. JAIN'S FAIRNESS INDEX (from flow statistics)
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def calculate_jains_fairness_index(values):
        """
        Calculate Jain's Fairness Index.

        Formula: JFI = (sum(x_i))^2 / (n * sum(x_i^2))
        Where:
            - 0 = perfectly unequal distribution
            - 1 = perfectly equal distribution
            - n = number of flows/paths

        Args:
            values: List of flow throughputs, packet counts, or byte counts

        Returns:
            Jain's Fairness Index (float between 0 and 1), or None if invalid
        """
        if not values or len(values) == 0:
            return None
        
        if len(values) == 1:
            return 1.0  # Single flow is perfectly "fair"
        
        # Filter out zero values (inactive flows)
        values = [v for v in values if v > 0]
        if not values:
            return None
        
        n = len(values)
        sum_values = sum(values)
        sum_squares = sum(v ** 2 for v in values)
        
        if sum_squares == 0:
            return None
        
        jfi = (sum_values ** 2) / (n * sum_squares)
        return round(jfi, 4)

    # ──────────────────────────────────────────────────────────────────────────
    # 4. ACTIVE PATHS (from switch flow statistics)
    # ──────────────────────────────────────────────────────────────────────────

    def poll_switch_statistics(self, src_mac, dst_mac, src_dpid, dst_dpid):
        """
        Poll OpenFlow switches for flow statistics.

        Queries all switches along the path to get packet/byte counts
        for the specific flow (src_mac -> dst_mac).

        Args:
            src_mac: Source MAC address
            dst_mac: Destination MAC address
            src_dpid: Source switch DPID
            dst_dpid: Destination switch DPID

        Returns:
            Dict with keys:
                - 'total_packets': Total packets for this flow
                - 'total_bytes': Total bytes for this flow
                - 'active_paths': Number of paths with traffic
                - 'per_switch_stats': Dict[dpid] = (packets, bytes)
        """
        self.logger.debug(f"[STATS-POLL] {src_mac} -> {dst_mac}")
        
        result = {
            'total_packets': 0,
            'total_bytes': 0,
            'active_paths': 0,
            'per_switch_stats': {},
            'path_byte_distribution': []
        }
        
        try:
            # Iterate through all connected switches
            for dpid, datapath in self.controller.datapaths.items():
                packets, bytes_count = self._get_flow_stats_from_switch(
                    datapath, src_mac, dst_mac
                )
                
                if packets > 0 or bytes_count > 0:
                    result['per_switch_stats'][dpid] = (packets, bytes_count)
                    result['total_packets'] += packets
                    result['total_bytes'] += bytes_count
                    result['active_paths'] += 1
                    result['path_byte_distribution'].append(bytes_count)
                    
                    self.logger.debug(
                        f"[STATS-SWITCH] s{dpid}: {packets} packets, {bytes_count} bytes"
                    )
        except Exception as e:
            self.logger.error(f"[STATS-ERROR] {e}")
        
        return result

    def _get_flow_stats_from_switch(self, datapath, src_mac, dst_mac):
        """
        Query a single switch for flow statistics matching (src_mac, dst_mac).

        Args:
            datapath: OpenFlow datapath object
            src_mac: Source MAC address
            dst_mac: Destination MAC address

        Returns:
            Tuple (total_packets, total_bytes) for all matching flows
        """
        try:
            from os_ken.ofproto import ofproto_v1_3
            from os_ken.controller import ofp_event
            
            ofproto = datapath.ofproto
            parser = datapath.ofproto_parser
            
            # Request flow statistics
            req = parser.OFPFlowStatsRequest(
                datapath=datapath,
                table_id=ofproto.OFPTT_ALL,
                out_port=ofproto.OFPP_ANY,
                out_group=ofproto.OFPG_ANY
            )
            
            # Send request synchronously
            datapath.send_msg(req)
            
            # Note: This is a simplified version. In real deployment,
            # you should use proper event handlers for async responses.
            # For now, return 0 as this needs async handling.
            return (0, 0)
            
        except Exception as e:
            self.logger.debug(f"[STATS-SWITCH-ERROR] {e}")
            return (0, 0)

    # ──────────────────────────────────────────────────────────────────────────
    # UNIFIED METRICS COLLECTION
    # ──────────────────────────────────────────────────────────────────────────

    def collect_flow_metrics(self, src_host, dst_host, src_mac, dst_mac, 
                            src_dpid, dst_dpid, flow_id=None):
        """
        Collect all 4 metrics for a flow.

        Args:
            src_host: Source host object (Mininet)
            dst_host: Destination host object (Mininet)
            src_mac: Source MAC address
            dst_mac: Destination MAC address
            src_dpid: Source switch DPID
            dst_dpid: Destination switch DPID
            flow_id: Optional flow identifier for logging

        Returns:
            Dict with all collected metrics
        """
        flow_key = (src_mac, dst_mac)
        flow_id_str = f" (flow {flow_id})" if flow_id else ""
        
        self.logger.info(f"[METRICS] Collecting metrics for {src_mac} -> {dst_mac}{flow_id_str}")
        
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'flow_id': flow_id,
            'src_mac': src_mac,
            'dst_mac': dst_mac,
            'src_dpid': src_dpid,
            'dst_dpid': dst_dpid,
            'src_host': src_host.name,
            'dst_host': dst_host.name,
        }
        
        # 1. Measure throughput (iperf3)
        throughput_mbps = self.measure_throughput(src_host, dst_host)
        metrics['throughput_mbps'] = throughput_mbps or 0.0
        
        # 2. Measure latency (ping)
        latency_ms = self.measure_latency(src_host, dst_host)
        metrics['latency_ms'] = latency_ms or 0.0
        
        # 3. Poll switch statistics
        stats = self.poll_switch_statistics(src_mac, dst_mac, src_dpid, dst_dpid)
        metrics['total_packets'] = stats['total_packets']
        metrics['total_bytes'] = stats['total_bytes']
        metrics['active_paths'] = stats['active_paths']
        metrics['per_switch_stats'] = stats['per_switch_stats']
        
        # 4. Calculate Jain's Fairness Index
        # Based on byte distribution across active paths
        if stats['path_byte_distribution']:
            jfi = self.calculate_jains_fairness_index(stats['path_byte_distribution'])
            metrics['jains_fairness_index'] = jfi or 0.0
        else:
            metrics['jains_fairness_index'] = 0.0
        
        # Store in cache
        self.flow_metrics[flow_key] = metrics
        
        self.logger.info(
            f"[METRICS-COLLECTED] {src_mac}->{dst_mac}: "
            f"throughput={metrics['throughput_mbps']}Mbps, "
            f"latency={metrics['latency_ms']}ms, "
            f"jfi={metrics['jains_fairness_index']}, "
            f"active_paths={metrics['active_paths']}"
        )
        
        return metrics

    def collect_multiple_flows(self, flows, duration_per_flow=10):
        """
        Collect metrics for multiple flows sequentially.

        Args:
            flows: List of tuples (src_host, dst_host, src_mac, dst_mac, src_dpid, dst_dpid)
            duration_per_flow: Duration of iperf3 test per flow

        Returns:
            List of metrics dicts
        """
        all_metrics = []
        
        for i, flow in enumerate(flows, 1):
            src_host, dst_host, src_mac, dst_mac, src_dpid, dst_dpid = flow
            
            self.logger.info(f"[FLOWS] Collecting flow {i}/{len(flows)}")
            metrics = self.collect_flow_metrics(
                src_host, dst_host, src_mac, dst_mac, src_dpid, dst_dpid, flow_id=i
            )
            all_metrics.append(metrics)
            
            # Brief pause between flows
            if i < len(flows):
                time.sleep(2)
        
        return all_metrics

    # ──────────────────────────────────────────────────────────────────────────
    # CSV EXPORT
    # ──────────────────────────────────────────────────────────────────────────

    def save_metrics_to_csv(self, metrics_list, multipath_enabled=None):
        """
        Save collected metrics to CSV file.

        Args:
            metrics_list: List of metrics dicts from collect_flow_metrics()
            multipath_enabled: Whether multipath forwarding was enabled
                               If None, uses self.multipath_enabled

        Returns:
            Path to saved CSV file
        """
        if not metrics_list:
            self.logger.warning("[CSV] No metrics to save")
            return None
        
        # Use self.multipath_enabled if not explicitly provided
        if multipath_enabled is None:
            multipath_enabled = self.multipath_enabled
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"metrics_{self.algorithm}_{timestamp}.csv"
        filepath = self.output_dir / filename
        
        # CSV columns
        fieldnames = [
            'timestamp',
            'flow_id',
            'src_mac',
            'dst_mac',
            'src_dpid',
            'dst_dpid',
            'src_host',
            'dst_host',
            'throughput_mbps',
            'latency_ms',
            'jains_fairness_index',
            'active_paths',
            'total_packets',
            'total_bytes',
            'algorithm',
            'multipath_enabled',
        ]
        
        try:
            with open(filepath, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for metrics in metrics_list:
                    row = {field: metrics.get(field, '') for field in fieldnames}
                    row['algorithm'] = self.algorithm
                    row['multipath_enabled'] = multipath_enabled
                    writer.writerow(row)
            
            self.logger.info(f"[CSV] Metrics saved to {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"[CSV-ERROR] {e}")
            return None

    def print_metrics_summary(self, metrics_list):
        """Print a summary of collected metrics to console."""
        if not metrics_list:
            print("No metrics collected")
            return
        
        print("\n" + "="*80)
        print(f"METRICS SUMMARY - Algorithm: {self.algorithm}")
        print("="*80)
        
        for i, m in enumerate(metrics_list, 1):
            print(f"\nFlow {i}: {m['src_host']} -> {m['dst_host']}")
            print(f"  Source MAC:               {m['src_mac']}")
            print(f"  Dest MAC:                 {m['dst_mac']}")
            print(f"  Throughput:               {m['throughput_mbps']:.2f} Mbps")
            print(f"  Latency (RTT):            {m['latency_ms']:.2f} ms")
            print(f"  Jain's Fairness Index:    {m['jains_fairness_index']:.4f}")
            print(f"  Active Paths:             {m['active_paths']}")
            print(f"  Total Packets:            {m['total_packets']}")
            print(f"  Total Bytes:              {m['total_bytes']}")
        
        print("\n" + "="*80)
        
        # Summary statistics
        throughputs = [m['throughput_mbps'] for m in metrics_list]
        latencies = [m['latency_ms'] for m in metrics_list]
        jfis = [m['jains_fairness_index'] for m in metrics_list]
        
        print("\nAVERAGE METRICS:")
        print(f"  Avg Throughput:           {sum(throughputs)/len(throughputs):.2f} Mbps")
        print(f"  Avg Latency:              {sum(latencies)/len(latencies):.2f} ms")
        print(f"  Avg Fairness Index:       {sum(jfis)/len(jfis):.4f}")
        print("="*80 + "\n")

    # ──────────────────────────────────────────────────────────────────────────
    # ALGORITHM TIMING AND LINK TRAFFIC EXPORT
    # ──────────────────────────────────────────────────────────────────────────

    def save_algorithm_times_to_csv(self):
        """Save algorithm calculation times to CSV.
        
        Returns:
            Path to saved CSV file
        """
        if not self.algorithm_times:
            self.logger.warning("[ALGO-CSV] No algorithm times to save")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"algo_times_{self.algorithm}_{timestamp}.csv"
        filepath = self.output_dir / filename
        
        fieldnames = ['src_mac', 'dst_mac', 'calculation_time_ms', 'algorithm', 'multipath_enabled']
        
        try:
            with open(filepath, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for (src_mac, dst_mac), calc_time in self.algorithm_times.items():
                    writer.writerow({
                        'src_mac': src_mac,
                        'dst_mac': dst_mac,
                        'calculation_time_ms': f"{calc_time:.3f}",
                        'algorithm': self.algorithm,
                        'multipath_enabled': self.multipath_enabled
                    })
            
            self.logger.info(f"[ALGO-CSV] Algorithm times saved to {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"[ALGO-CSV-ERROR] {e}")
            return None

    def save_link_traffic_to_csv(self, run_number=None):
        """Save per-link traffic distribution to CSV.
        
        Extracts link traffic from the controller's actual flow statistics.
        
        Args:
            run_number: Optional run number for multi-run tracking
        
        Returns:
            Path to saved CSV file
        """
        link_traffic = self.get_link_traffic_summary()
        
        if not link_traffic:
            self.logger.warning("[LINK-CSV] No link traffic data to save")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"link_traffic_{self.algorithm}_{timestamp}.csv"
        filepath = self.output_dir / filename
        
        # Determine fieldnames based on actual link data structure
        fieldnames = ['run_number', 'src_switch', 'out_port', 'dst_switch', 
                      'total_bytes', 'algorithm', 'multipath_enabled']
        
        try:
            with open(filepath, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for (src_dpid, out_port, dst_dpid), byte_count in link_traffic.items():
                    writer.writerow({
                        'run_number': run_number or 'N/A',
                        'src_switch': f"s{src_dpid}",
                        'out_port': out_port,
                        'dst_switch': f"s{dst_dpid}" if dst_dpid else "host",
                        'total_bytes': byte_count,
                        'algorithm': self.algorithm,
                        'multipath_enabled': self.multipath_enabled
                    })
            
            self.logger.info(f"[LINK-CSV] Link traffic saved to {filepath} ({len(link_traffic)} links)")
            return filepath
            
        except Exception as e:
            self.logger.error(f"[LINK-CSV-ERROR] {e}")
            return None

    def save_multi_run_summary(self, output_filename=None):
        """Save summary of metrics from multiple runs with averages.
        
        Args:
            output_filename: Optional custom output filename
        
        Returns:
            Path to saved CSV file
        """
        if not self.run_metrics:
            self.logger.warning("[MULTI-RUN] No run metrics to save")
            return None
        
        if output_filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"multi_run_summary_{self.algorithm}_{timestamp}.csv"
        
        filepath = self.output_dir / output_filename
        
        fieldnames = ['run_number', 'throughput_mbps', 'latency_ms', 'jains_fairness_index', 
                      'active_paths', 'algorithm', 'multipath_enabled']
        
        try:
            with open(filepath, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for metrics in self.run_metrics:
                    row = {field: metrics.get(field, '') for field in fieldnames}
                    row['algorithm'] = self.algorithm
                    row['multipath_enabled'] = self.multipath_enabled
                    writer.writerow(row)
            
            # Calculate and log averages
            if self.run_metrics:
                throughputs = [m.get('throughput_mbps', 0) for m in self.run_metrics]
                latencies = [m.get('latency_ms', 0) for m in self.run_metrics]
                jfis = [m.get('jains_fairness_index', 0) for m in self.run_metrics]
                
                avg_throughput = sum(throughputs) / len(throughputs) if throughputs else 0
                avg_latency = sum(latencies) / len(latencies) if latencies else 0
                avg_jfi = sum(jfis) / len(jfis) if jfis else 0
                
                self.logger.info(f"[MULTI-RUN] Summary saved to {filepath}")
                self.logger.info(f"[MULTI-RUN] Avg Throughput: {avg_throughput:.2f} Mbps")
                self.logger.info(f"[MULTI-RUN] Avg Latency: {avg_latency:.2f} ms")
                self.logger.info(f"[MULTI-RUN] Avg Fairness Index: {avg_jfi:.4f}")
            
            return filepath
            
        except Exception as e:
            self.logger.error(f"[MULTI-RUN-ERROR] {e}")
            return None


# ──────────────────────────────────────────────────────────────────────────────
# ASYNC STATISTICS COLLECTOR (for integration with controller)
# ──────────────────────────────────────────────────────────────────────────────

class AsyncFlowStatsCollector:
    """
    Asynchronous flow statistics collector for OpenFlow switches.
    
    Use this class to collect statistics periodically from switches
    without blocking the controller's main event loop.
    """

    def __init__(self, controller, poll_interval=5):
        """
        Initialize async statistics collector.

        Args:
            controller: SPFBaseController instance
            poll_interval: Polling interval in seconds
        """
        self.controller = controller
        self.poll_interval = poll_interval
        self.logger = logging.getLogger(__name__)
        
        # Flow statistics storage: (dpid, eth_src, eth_dst) -> FlowStats
        self.flow_stats = {}

    class FlowStats:
        """Container for per-flow statistics."""
        def __init__(self):
            self.packet_count = 0
            self.byte_count = 0
            self.duration_sec = 0
            self.duration_nsec = 0
            self.priority = 0
            self.idle_timeout = 0
            self.hard_timeout = 0
            self.last_updated = time.time()

    def handle_flow_stats_reply(self, dpid, flows):
        """
        Handle OFPFlowStatsReply from a switch.

        Args:
            dpid: Datapath ID
            flows: List of OFPFlowStats objects
        """
        for flow in flows:
            try:
                match = flow.match
                
                # Extract MAC addresses if they exist in match
                eth_src = match.get('eth_src')
                eth_dst = match.get('eth_dst')
                
                if eth_src and eth_dst:
                    key = (dpid, eth_src, eth_dst)
                    
                    stats = self.FlowStats()
                    stats.packet_count = flow.packet_count
                    stats.byte_count = flow.byte_count
                    stats.duration_sec = flow.duration_sec
                    stats.duration_nsec = flow.duration_nsec
                    stats.priority = flow.priority
                    stats.idle_timeout = flow.idle_timeout
                    stats.hard_timeout = flow.hard_timeout
                    
                    self.flow_stats[key] = stats
                    
                    self.logger.debug(
                        f"[ASYNC-STATS] s{dpid}: {eth_src}->{eth_dst}: "
                        f"{flow.packet_count}pkt, {flow.byte_count}B"
                    )
            except Exception as e:
                self.logger.debug(f"[ASYNC-STATS-PARSE] {e}")

    def get_flow_stats(self, eth_src, eth_dst):
        """
        Get aggregated statistics for a flow across all switches.

        Args:
            eth_src: Source MAC address
            eth_dst: Destination MAC address

        Returns:
            Dict with total_packets, total_bytes, and per_switch breakdown
        """
        result = {
            'total_packets': 0,
            'total_bytes': 0,
            'per_switch': {}
        }
        
        for (dpid, src_mac, dst_mac), stats in self.flow_stats.items():
            if src_mac == eth_src and dst_mac == eth_dst:
                result['total_packets'] += stats.packet_count
                result['total_bytes'] += stats.byte_count
                result['per_switch'][dpid] = {
                    'packets': stats.packet_count,
                    'bytes': stats.byte_count
                }
        
        return result

