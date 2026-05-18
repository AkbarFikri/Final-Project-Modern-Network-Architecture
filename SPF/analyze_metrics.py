#!/usr/bin/env python3
"""
Analyze and visualize metrics from CSV files.

Generates comparison plots for:
- Active paths per algorithm/mode
- Total traffic (bytes/packets)
- Jain's Fairness Index
- Algorithm performance comparison

Usage:
    python analyze_metrics.py [metrics_dir]
    python analyze_metrics.py metrics/
    python analyze_metrics.py metrics/ --output plots/
"""

import csv
import sys
import os
from pathlib import Path
from collections import defaultdict
import argparse
import statistics

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None

try:
    import matplotlib.pyplot as plt
    import pandas as pd
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("[WARNING] matplotlib/pandas not available. Install with: pip install matplotlib pandas")


def mean(values):
    """Compute mean, with fallback to statistics module."""
    if not values:
        return 0
    if HAS_NUMPY:
        return float(np.mean(values))
    else:
        return float(statistics.mean(values))


class MetricsAnalyzer:
    """Analyze metrics from CSV files."""
    
    def __init__(self, metrics_dir="metrics"):
        """Initialize analyzer with metrics directory."""
        self.metrics_dir = Path(metrics_dir)
        self.data = {}  # {algorithm: {multipath: [records]}}
        self.load_all_metrics()
    
    def load_all_metrics(self):
        """Load all CSV files from metrics directory."""
        if not self.metrics_dir.exists():
            print(f"[ERROR] Metrics directory not found: {self.metrics_dir}")
            return
        
        csv_files = sorted(self.metrics_dir.glob("metrics_*.csv"))
        print(f"[LOAD] Found {len(csv_files)} CSV file(s)")
        
        for csv_file in csv_files:
            print(f"[LOAD] Reading {csv_file.name}...")
            self._load_csv(csv_file)
    
    def _load_csv(self, csv_file):
        """Load a single CSV file."""
        try:
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Skip empty rows
                    if not row.get('src_mac'):
                        continue
                    
                    algorithm = row.get('algorithm', 'unknown')
                    multipath = row.get('multipath_enabled', 'False').lower() == 'true'
                    
                    key = (algorithm, multipath)
                    if key not in self.data:
                        self.data[key] = []
                    
                    try:
                        # Parse numeric fields
                        record = {
                            'src_mac': row['src_mac'],
                            'dst_mac': row['dst_mac'],
                            'flow_id': row.get('flow_id', ''),
                            'throughput_mbps': float(row.get('throughput_mbps', 0)),
                            'latency_ms': float(row.get('latency_ms', 0)),
                            'jains_fairness_index': float(row.get('jains_fairness_index', 0)),
                            'active_paths': int(row.get('active_paths', 1)),
                            'total_packets': int(row.get('total_packets', 0)),
                            'total_bytes': int(row.get('total_bytes', 0)),
                        }
                        self.data[key].append(record)
                    except (ValueError, TypeError) as e:
                        print(f"[WARN] Skipping malformed row: {e}")
                        continue
        
        except Exception as e:
            print(f"[ERROR] Failed to load {csv_file}: {e}")
    
    def print_summary(self):
        """Print summary statistics."""
        print("\n" + "="*80)
        print("METRICS SUMMARY")
        print("="*80)
        
        for (algorithm, multipath), records in sorted(self.data.items()):
            mode = "MULTIPATH" if multipath else "SINGLE-PATH"
            print(f"\n{algorithm.upper()} ({mode}):")
            print(f"  Flows:                    {len(records)}")
            
            if records:
                total_packets = sum(r['total_packets'] for r in records)
                total_bytes = sum(r['total_bytes'] for r in records)
                avg_active_paths = mean([r['active_paths'] for r in records])
                avg_jfi = mean([r['jains_fairness_index'] for r in records])
                
                print(f"  Total Packets:            {total_packets:,}")
                print(f"  Total Bytes:              {total_bytes:,}")
                print(f"  Avg Active Paths:         {avg_active_paths:.2f}")
                print(f"  Avg Fairness Index:       {avg_jfi:.4f}")
                
                # Traffic distribution across flows
                bytes_per_flow = [r['total_bytes'] for r in records]
                if bytes_per_flow:
                    print(f"  Min Bytes/Flow:           {min(bytes_per_flow):,}")
                    print(f"  Max Bytes/Flow:           {max(bytes_per_flow):,}")
                    print(f"  Avg Bytes/Flow:           {mean(bytes_per_flow):,.0f}")
    
    def compare_algorithms(self):
        """Compare all algorithms in both modes."""
        print("\n" + "="*80)
        print("ALGORITHM COMPARISON")
        print("="*80)
        
        algorithms = set(algo for algo, _ in self.data.keys())
        
        for algorithm in sorted(algorithms):
            print(f"\n{algorithm.upper()}:")
            
            single_path = self.data.get((algorithm, False), [])
            multipath = self.data.get((algorithm, True), [])
            
            if single_path:
                single_bytes = sum(r['total_bytes'] for r in single_path)
                single_jfi = mean([r['jains_fairness_index'] for r in single_path])
                print(f"  Single-Path:")
                print(f"    - Total Bytes:            {single_bytes:,}")
                print(f"    - Avg Fairness:           {single_jfi:.4f}")
            
            if multipath:
                multi_bytes = sum(r['total_bytes'] for r in multipath)
                multi_jfi = mean([r['jains_fairness_index'] for r in multipath])
                multi_paths = mean([r['active_paths'] for r in multipath])
                print(f"  Multipath (ECMP):")
                print(f"    - Total Bytes:            {multi_bytes:,}")
                print(f"    - Avg Fairness:           {multi_jfi:.4f}")
                print(f"    - Avg Paths:              {multi_paths:.2f}")
                
                if single_path:
                    bytes_increase = ((multi_bytes - single_bytes) / single_bytes * 100) if single_bytes > 0 else 0
                    print(f"    - Throughput Change:      {bytes_increase:+.1f}%")
    
    def generate_plots(self, output_dir="plots"):
        """Generate visualization plots."""
        if not HAS_MATPLOTLIB:
            print("[ERROR] matplotlib not available for plotting")
            return
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 1. Active Paths per Flow
        self._plot_active_paths(output_path)
        
        # 2. Fairness Index Comparison
        self._plot_fairness(output_path)
        
        # 3. Traffic Distribution
        self._plot_traffic(output_path)
        
        # 4. Algorithm Comparison
        self._plot_comparison(output_path)
        
        print(f"\n[PLOTS] Saved to {output_path}/")
    
    def _plot_active_paths(self, output_path):
        """Plot active paths per algorithm."""
        fig, ax = plt.subplots(figsize=(10, 6))
        
        algorithms = sorted(set(algo for algo, _ in self.data.keys()))
        if HAS_NUMPY:
            x_pos = np.arange(len(algorithms))
        else:
            x_pos = list(range(len(algorithms)))
        width = 0.35
        
        single_paths = []
        multi_paths = []
        
        for algorithm in algorithms:
            single = self.data.get((algorithm, False), [])
            multi = self.data.get((algorithm, True), [])
            
            single_paths.append(mean([r['active_paths'] for r in single]) if single else 0)
            multi_paths.append(mean([r['active_paths'] for r in multi]) if multi else 0)
        
        if HAS_NUMPY:
            ax.bar(x_pos - width/2, single_paths, width, label='Single-Path', alpha=0.8)
            ax.bar(x_pos + width/2, multi_paths, width, label='Multipath (ECMP)', alpha=0.8)
        else:
            ax.bar([p - width/2 for p in x_pos], single_paths, width, label='Single-Path', alpha=0.8)
            ax.bar([p + width/2 for p in x_pos], multi_paths, width, label='Multipath (ECMP)', alpha=0.8)
        
        ax.set_ylabel('Average Active Paths', fontsize=12)
        ax.set_title('Active Paths per Algorithm', fontsize=14, fontweight='bold')
        ax.set_xticks(x_pos)
        ax.set_xticklabels(algorithms)
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_path / "01_active_paths.png", dpi=150)
        print(f"[PLOT] Saved: 01_active_paths.png")
        plt.close()
    
    def _plot_fairness(self, output_path):
        """Plot Jain's Fairness Index comparison."""
        fig, ax = plt.subplots(figsize=(10, 6))
        
        algorithms = sorted(set(algo for algo, _ in self.data.keys()))
        if HAS_NUMPY:
            x_pos = np.arange(len(algorithms))
        else:
            x_pos = list(range(len(algorithms)))
        width = 0.35
        
        single_jfi = []
        multi_jfi = []
        
        for algorithm in algorithms:
            single = self.data.get((algorithm, False), [])
            multi = self.data.get((algorithm, True), [])
            
            single_jfi.append(mean([r['jains_fairness_index'] for r in single]) if single else 0)
            multi_jfi.append(mean([r['jains_fairness_index'] for r in multi]) if multi else 0)
        
        if HAS_NUMPY:
            ax.bar(x_pos - width/2, single_jfi, width, label='Single-Path', alpha=0.8)
            ax.bar(x_pos + width/2, multi_jfi, width, label='Multipath (ECMP)', alpha=0.8)
        else:
            ax.bar([p - width/2 for p in x_pos], single_jfi, width, label='Single-Path', alpha=0.8)
            ax.bar([p + width/2 for p in x_pos], multi_jfi, width, label='Multipath (ECMP)', alpha=0.8)
        
        ax.set_ylabel("Jain's Fairness Index", fontsize=12)
        ax.set_title("Load Balance Fairness Comparison", fontsize=14, fontweight='bold')
        ax.set_xticks(x_pos)
        ax.set_xticklabels(algorithms)
        ax.set_ylim([0, 1.1])
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_path / "02_fairness_index.png", dpi=150)
        print(f"[PLOT] Saved: 02_fairness_index.png")
        plt.close()
    
    def _plot_traffic(self, output_path):
        """Plot traffic distribution."""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        
        algorithms = sorted(set(algo for algo, _ in self.data.keys()))
        
        # Total bytes
        total_bytes_data = {}
        for algorithm in algorithms:
            single = self.data.get((algorithm, False), [])
            multi = self.data.get((algorithm, True), [])
            total_bytes_data[algorithm] = {
                'single': sum(r['total_bytes'] for r in single),
                'multi': sum(r['total_bytes'] for r in multi)
            }
        
        if HAS_NUMPY:
            x_pos = np.arange(len(algorithms))
        else:
            x_pos = list(range(len(algorithms)))
        width = 0.35
        
        single_bytes = [total_bytes_data[a]['single'] for a in algorithms]
        multi_bytes = [total_bytes_data[a]['multi'] for a in algorithms]
        
        if HAS_NUMPY:
            ax1.bar(x_pos - width/2, [b/1e6 for b in single_bytes], width, label='Single-Path', alpha=0.8)
            ax1.bar(x_pos + width/2, [b/1e6 for b in multi_bytes], width, label='Multipath (ECMP)', alpha=0.8)
        else:
            ax1.bar([p - width/2 for p in x_pos], [b/1e6 for b in single_bytes], width, label='Single-Path', alpha=0.8)
            ax1.bar([p + width/2 for p in x_pos], [b/1e6 for b in multi_bytes], width, label='Multipath (ECMP)', alpha=0.8)
        
        ax1.set_ylabel('Total Traffic (MB)', fontsize=12)
        ax1.set_title('Total Traffic per Algorithm', fontsize=12, fontweight='bold')
        ax1.set_xticks(x_pos)
        ax1.set_xticklabels(algorithms)
        ax1.legend()
        ax1.grid(axis='y', alpha=0.3)
        
        # Packets
        total_packets_data = {}
        for algorithm in algorithms:
            single = self.data.get((algorithm, False), [])
            multi = self.data.get((algorithm, True), [])
            total_packets_data[algorithm] = {
                'single': sum(r['total_packets'] for r in single),
                'multi': sum(r['total_packets'] for r in multi)
            }
        
        single_packets = [total_packets_data[a]['single'] for a in algorithms]
        multi_packets = [total_packets_data[a]['multi'] for a in algorithms]
        
        if HAS_NUMPY:
            ax2.bar(x_pos - width/2, [p/1e3 for p in single_packets], width, label='Single-Path', alpha=0.8)
            ax2.bar(x_pos + width/2, [p/1e3 for p in multi_packets], width, label='Multipath (ECMP)', alpha=0.8)
        else:
            ax2.bar([p - width/2 for p in x_pos], [p/1e3 for p in single_packets], width, label='Single-Path', alpha=0.8)
            ax2.bar([p + width/2 for p in x_pos], [p/1e3 for p in multi_packets], width, label='Multipath (ECMP)', alpha=0.8)
        
        ax2.set_ylabel('Total Packets (K)', fontsize=12)
        ax2.set_title('Total Packets per Algorithm', fontsize=12, fontweight='bold')
        ax2.set_xticks(x_pos)
        ax2.set_xticklabels(algorithms)
        ax2.legend()
        ax2.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_path / "03_traffic_distribution.png", dpi=150)
        print(f"[PLOT] Saved: 03_traffic_distribution.png")
        plt.close()
    
    def _plot_comparison(self, output_path):
        """Multi-metric comparison."""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        algorithms = sorted(set(algo for algo, _ in self.data.keys()))
        
        # Prepare data
        metrics = {
            'active_paths': [],
            'fairness': [],
            'total_bytes': [],
            'avg_bytes_per_flow': []
        }
        
        for algorithm in algorithms:
            single = self.data.get((algorithm, False), [])
            multi = self.data.get((algorithm, True), [])
            
            # Active paths
            ax = axes[0, 0]
            single_paths = np.mean([r['active_paths'] for r in single]) if single else 0
            multi_paths = np.mean([r['active_paths'] for r in multi]) if multi else 0
            
            x = len(ax.patches) // 2
            ax.bar([x*2, x*2+1], [single_paths, multi_paths], alpha=0.8)
        
        # Simpler comparison
        ax = axes[0, 0]
        for i, algorithm in enumerate(algorithms):
            single = self.data.get((algorithm, False), [])
            multi = self.data.get((algorithm, True), [])
            
            single_paths = mean([r['active_paths'] for r in single]) if single else 1
            multi_paths = mean([r['active_paths'] for r in multi]) if multi else 1
            
            ax.plot(i, single_paths, 'o', markersize=10, label='Single' if i == 0 else '')
            ax.plot(i, multi_paths, 's', markersize=10, label='Multi' if i == 0 else '')
        
        ax.set_ylabel('Average Active Paths')
        ax.set_title('Active Paths')
        ax.set_xticks(range(len(algorithms)))
        ax.set_xticklabels(algorithms)
        ax.grid(alpha=0.3)
        
        # Fairness Index
        ax = axes[0, 1]
        for i, algorithm in enumerate(algorithms):
            single = self.data.get((algorithm, False), [])
            multi = self.data.get((algorithm, True), [])
            
            single_jfi = mean([r['jains_fairness_index'] for r in single]) if single else 0
            multi_jfi = mean([r['jains_fairness_index'] for r in multi]) if multi else 0
            
            ax.plot(i, single_jfi, 'o', markersize=10, label='Single' if i == 0 else '')
            ax.plot(i, multi_jfi, 's', markersize=10, label='Multi' if i == 0 else '')
        
        ax.set_ylabel("Jain's Fairness Index")
        ax.set_title('Fairness Index')
        ax.set_xticks(range(len(algorithms)))
        ax.set_xticklabels(algorithms)
        ax.set_ylim([0, 1.1])
        ax.grid(alpha=0.3)
        ax.legend()
        
        # Total Traffic
        ax = axes[1, 0]
        for i, algorithm in enumerate(algorithms):
            single = self.data.get((algorithm, False), [])
            multi = self.data.get((algorithm, True), [])
            
            single_bytes = sum(r['total_bytes'] for r in single) / 1e6 if single else 0
            multi_bytes = sum(r['total_bytes'] for r in multi) / 1e6 if multi else 0
            
            ax.plot(i, single_bytes, 'o', markersize=10)
            ax.plot(i, multi_bytes, 's', markersize=10)
        
        ax.set_ylabel('Total Traffic (MB)')
        ax.set_title('Total Traffic')
        ax.set_xticks(range(len(algorithms)))
        ax.set_xticklabels(algorithms)
        ax.grid(alpha=0.3)
        
        # Flows count
        ax = axes[1, 1]
        for i, algorithm in enumerate(algorithms):
            single = self.data.get((algorithm, False), [])
            multi = self.data.get((algorithm, True), [])
            
            ax.plot(i, len(single), 'o', markersize=10, label='Single' if i == 0 else '')
            ax.plot(i, len(multi), 's', markersize=10, label='Multi' if i == 0 else '')
        
        ax.set_ylabel('Flow Count')
        ax.set_title('Number of Flows')
        ax.set_xticks(range(len(algorithms)))
        ax.set_xticklabels(algorithms)
        ax.grid(alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_path / "04_detailed_comparison.png", dpi=150)
        print(f"[PLOT] Saved: 04_detailed_comparison.png")
        plt.close()


def main():
    parser = argparse.ArgumentParser(description='Analyze metrics from CSV files')
    parser.add_argument('metrics_dir', nargs='?', default='metrics', help='Metrics directory (default: metrics/)')
    parser.add_argument('--output', '-o', default='plots', help='Output directory for plots (default: plots/)')
    parser.add_argument('--no-plots', action='store_true', help='Skip plot generation')
    
    args = parser.parse_args()
    
    print(f"[INIT] Metrics directory: {args.metrics_dir}")
    print(f"[INIT] Output directory:  {args.output}")
    
    analyzer = MetricsAnalyzer(args.metrics_dir)
    
    if not analyzer.data:
        print("[ERROR] No metrics data loaded")
        return 1
    
    analyzer.print_summary()
    analyzer.compare_algorithms()
    
    if not args.no_plots:
        analyzer.generate_plots(args.output)
    
    print("\n[DONE] Analysis complete!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
