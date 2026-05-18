#!/bin/bash
# collect_test_results.sh
# Helper script to organize and archive test results

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="test_results_${TIMESTAMP}"
ALGORITHM="${1:-unknown}"
MODE="${2:-unknown}"

echo "=========================================="
echo "Test Results Collector"
echo "=========================================="
echo "Timestamp: ${TIMESTAMP}"
echo "Algorithm: ${ALGORITHM}"
echo "Mode: ${MODE}"
echo ""

# Create results directory
mkdir -p "${RESULTS_DIR}"
echo "[COLLECT] Created directory: ${RESULTS_DIR}"

# Copy metrics CSVs
if [ -d "metrics" ] && [ "$(ls metrics/metrics_*.csv 2>/dev/null | wc -l)" -gt 0 ]; then
    cp metrics/metrics_*.csv "${RESULTS_DIR}/"
    echo "[COLLECT] Copied $(ls metrics/metrics_*.csv 2>/dev/null | wc -l) CSV file(s)"
else
    echo "[WARN] No metrics CSV files found"
fi

# Copy logs
if [ -d "logs" ] && [ "$(ls logs/* 2>/dev/null | wc -l)" -gt 0 ]; then
    cp logs/* "${RESULTS_DIR}/" 2>/dev/null
    echo "[COLLECT] Copied logs/"
else
    echo "[WARN] No logs found"
fi

# Copy plots
if [ -d "plots" ] && [ "$(ls plots/*.png 2>/dev/null | wc -l)" -gt 0 ]; then
    cp plots/*.png "${RESULTS_DIR}/" 2>/dev/null
    echo "[COLLECT] Copied plots/"
else
    echo "[WARN] No plots found"
fi

# Create summary file
cat > "${RESULTS_DIR}/TEST_SUMMARY.txt" << EOF
Test Results Summary
====================
Timestamp: ${TIMESTAMP}
Algorithm: ${ALGORITHM}
Mode: ${MODE}

Directory Contents:
- metrics_*.csv: Controller metrics (flows, throughput, fairness, active paths)
- iperf3_test*.log: Throughput measurements
- ping_test*.log: Latency measurements
- tcpdump_*.pcap: Network packet captures
- *.png: Analysis plots

Analysis Steps:
1. Run: python SPF/analyze_metrics.py $(pwd)/${RESULTS_DIR} --output ${RESULTS_DIR}/plots/
2. Export: python SPF/export_metrics.py $(pwd)/${RESULTS_DIR} --format html --output ${RESULTS_DIR}/report.html
3. View HTML report in browser for detailed analysis

File Sizes:
$(du -sh "${RESULTS_DIR}"/* 2>/dev/null | sort -h || echo "N/A")

Test Date: $(date)
EOF

echo "[COLLECT] Created TEST_SUMMARY.txt"

# Display final structure
echo ""
echo "Results collected in: ${RESULTS_DIR}/"
echo ""
echo "Contents:"
ls -lh "${RESULTS_DIR}/" 2>/dev/null | tail -n +2 || echo "(empty)"

echo ""
echo "[DONE] Test results collection complete!"
echo "Analyze with: python SPF/analyze_metrics.py ${RESULTS_DIR}/"
