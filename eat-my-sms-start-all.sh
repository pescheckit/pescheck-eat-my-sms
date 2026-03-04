#!/bin/bash
# Auto-start eat-my-sms services for all detected USB serial devices

set -e

# Configuration
CONFIG_FILE="/etc/eat-my-sms/devices.conf"
MAX_DEVICES=8
DEVICE_PATTERN="ttyUSB*"

# Load config if exists
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

echo "Looking for devices matching: /dev/$DEVICE_PATTERN (max: $MAX_DEVICES)"

# Find all matching devices
DEVICES=$(ls /dev/$DEVICE_PATTERN 2>/dev/null | head -n $MAX_DEVICES || true)

if [ -z "$DEVICES" ]; then
    echo "No devices found matching /dev/$DEVICE_PATTERN"
    exit 0
fi

# Start service for each device
for device_path in $DEVICES; do
    device=$(basename "$device_path")
    echo "Starting eat-my-sms@${device}.service..."
    systemctl start "eat-my-sms@${device}.service" || echo "  Failed to start $device (no SIM card?)"
done

echo "Done. Check status with: systemctl status 'eat-my-sms@*.service'"
