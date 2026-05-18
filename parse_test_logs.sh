#!/bin/bash
# parse_test_logs.sh
# Helper script to extract and summarize metrics from iperf3 and ping logs

if [ $# -lt 1 ]; then
    echo "Usage: $0 <results_directory>"
    echo ""
    echo "Parses iperf3 and ping logs to extract key metrics"
    echo ""
    echo "Example:"
    echo "  $0 test_results_20260518_110000/"
    exit 1
fi

RESULTS_DIR="$1"

if [ ! -d "${RESULTS_DIR}" ]; then
    echo "[ERROR] Directory not found: ${RESULTS_DIR}"
    exit 1
fi

echo "==========================================="
echo "Test Logs Parser"
echo "==========================================="
echo "Directory: ${RESULTS_DIR}"
echo ""

# Parse iperf3 logs
echo "=== IPERF3 THROUGHPUT RESULTS ==="
echo ""

for log in "${RESULTS_DIR}"/iperf3_*.log; do
    if [ -f "${log}" ]; then
        filename=$(basename "${log}")
        echo "File: ${filename}"
        
        # Extract total transfer
        total_transfer=$(grep "sender" "${log}" 2>/dev/null | tail -1 | awk '{print $4, $5}')
        if [ -z "${total_transfer}" ]; then
            total_transfer=$(grep "SUM" "${log}" 2>/dev/null | tail -1 | awk '{print $4, $5}')
        fi
        
        # Extract bitrate
        bitrate=$(grep "sender" "${log}" 2>/dev/null | tail -1 | awk '{print $6, $7}')
        if [ -z "${bitrate}" ]; then
            bitrate=$(grep "SUM" "${log}" 2>/dev/null | tail -1 | awk '{print $6, $7}')
        fi
        
        # Extract retransmissions
        retrans=$(grep "Retr" "${log}" 2>/dev/null | tail -1 | awk '{print $4}')
        if [ -z "${retrans}" ]; then
            retrans=$(grep "^\[" "${log}" 2>/dev/null | tail -1 | awk '{print $NF}')
        fi
        
        echo "  Transfer: ${total_transfer}"
        echo "  Bitrate: ${bitrate}"
        echo "  Retransmissions: ${retrans}"
        echo ""
    fi
done

# Parse ping logs
echo "=== PING LATENCY RESULTS ==="
echo ""

for log in "${RESULTS_DIR}"/ping_*.log; do
    if [ -f "${log}" ]; then
        filename=$(basename "${log}")
        echo "File: ${filename}"
        
        # Extract min/avg/max/mdev
        stats=$(grep "min/avg/max" "${log}" 2>/dev/null)
        if [ -n "${stats}" ]; then
            min=$(echo "${stats}" | cut -d'=' -f2 | awk '{print $1}')
            avg=$(echo "${stats}" | cut -d'/' -f2)
            max=$(echo "${stats}" | cut -d'/' -f3)
            mdev=$(echo "${stats}" | cut -d'/' -f4)
            
            echo "  Min: ${min} ms"
            echo "  Avg: ${avg} ms"
            echo "  Max: ${max} ms"
            echo "  Mdev: ${mdev} ms"
        fi
        
        # Extract loss
        loss=$(grep "% packet loss" "${log}" 2>/dev/null | awk '{print $6}')
        if [ -n "${loss}" ]; then
            echo "  Loss: ${loss}"
        fi
        
        echo ""
    fi
done

# Parse CSV metrics
echo "=== CONTROLLER METRICS SUMMARY ==="
echo ""

csv_count=$(ls "${RESULTS_DIR}"/metrics_*.csv 2>/dev/null | wc -l)
if [ ${csv_count} -gt 0 ]; then
    echo "Found ${csv_count} metrics CSV file(s)"
    echo ""
    
    # Read first CSV and extract summary
    for csv in "${RESULTS_DIR}"/metrics_*.csv; do
        if [ -f "${csv}" ]; then
            filename=$(basename "${csv}")
            echo "File: ${filename}"
            
            # Count flows
            flow_count=$(tail -n +2 "${csv}" 2>/dev/null | grep -v "^," | wc -l)
            echo "  Flows: ${flow_count}"
            
            # Extract algorithm and multipath from first data row
            first_row=$(tail -n +2 "${csv}" 2>/dev/null | head -1)
            algorithm=$(echo "${first_row}" | cut -d',' -f15 | tr -d ' ')
            multipath=$(echo "${first_row}" | cut -d',' -f16 | tr -d ' ')
            
            echo "  Algorithm: ${algorithm}"
            echo "  Multipath: ${multipath}"
            
            # Sum total bytes
            total_bytes=$(tail -n +2 "${csv}" 2>/dev/null | grep -v "^," | cut -d',' -f14 | paste -sd+ | bc 2>/dev/null)
            if [ -n "${total_bytes}" ]; then
                total_mb=$(echo "scale=2; ${total_bytes} / 1048576" | bc)
                echo "  Total Traffic: ${total_mb} MB (${total_bytes} bytes)"
            fi
            
            # Average fairness index
            avg_jfi=$(tail -n +2 "${csv}" 2>/dev/null | grep -v "^," | cut -d',' -f11 | awk '{sum+=$1; count++} END {if (count>0) printf "%.4f\n", sum/count}')
            if [ -n "${avg_jfi}" ]; then
                echo "  Avg Fairness Index: ${avg_jfi}"
            fi
            
            # Average active paths
            avg_paths=$(tail -n +2 "${csv}" 2>/dev/null | grep -v "^," | cut -d',' -f12 | awk '{sum+=$1; count++} END {if (count>0) printf "%.2f\n", sum/count}')
            if [ -n "${avg_paths}" ]; then
                echo "  Avg Active Paths: ${avg_paths}"
            fi
            
            echo ""
        fi
    done
else
    echo "[WARN] No CSV metrics files found"
fi

# tcpdump packet count
echo "=== NETWORK CAPTURE SUMMARY ==="
echo ""

pcap_count=$(ls "${RESULTS_DIR}"/tcpdump_*.pcap 2>/dev/null | wc -l)
if [ ${pcap_count} -gt 0 ]; then
    for pcap in "${RESULTS_DIR}"/tcpdump_*.pcap; do
        if [ -f "${pcap}" ]; then
            filename=$(basename "${pcap}")
            size=$(du -h "${pcap}" | awk '{print $1}')
            packets=$(tcpdump -r "${pcap}" 2>/dev/null | wc -l)
            
            echo "File: ${filename}"
            echo "  Size: ${size}"
            echo "  Packets: ${packets}"
            echo ""
        fi
    done
else
    echo "[WARN] No tcpdump files found"
fi

echo "==========================================="
echo "Parse complete!"
