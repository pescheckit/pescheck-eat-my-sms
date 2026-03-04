# Eat My SMS

A daemon to work with 8-way GSM modem hubs to read SMS messages and send them to a webhook.

## Features

- 🔄 Automatic retry logic with exponential backoff
- ⚡ 115200 baud rate support for modern USB hubs
- 🔧 Graceful error handling - continues on failures
- 📊 Prometheus metrics support
- 📦 Multi-architecture packages (amd64, arm64)

## Hardware Support

**Designed for 8-way USB GSM modem hubs:**
- Exar XR21V1414 4-channel UART (2 chips = 8 ports)
- Baud rate: 115200
- Device names: `ttyUSB0` through `ttyUSB7`
- Also works with direct USB modems: `ttyACM0`, `ttyACM1`, etc.
- Configurable for any number of devices (default: 8)

## Installation

### From APT Repository (Recommended)

```bash
# Import GPG key
curl -fsSL https://pescheckit.github.io/eat-my-sms/apt/public.key | \
  sudo gpg --dearmor -o /etc/apt/keyrings/eat-my-sms.gpg

# Add repository (specify architectures to avoid i386 warnings)
echo "deb [arch=amd64,arm64 signed-by=/etc/apt/keyrings/eat-my-sms.gpg] https://pescheckit.github.io/eat-my-sms/apt stable main" | \
  sudo tee /etc/apt/sources.list.d/eat-my-sms.list

# Install
sudo apt update
sudo apt install eat-my-sms
```

### From GitHub Releases (Manual)

```bash
# Download latest release
VERSION="1.0.7"
ARCH="amd64"  # or "arm64"

wget https://github.com/pescheckit/eat-my-sms/releases/download/v${VERSION}/eat-my-sms_${VERSION}_${ARCH}.deb
sudo dpkg -i eat-my-sms_${VERSION}_${ARCH}.deb
sudo apt --fix-broken install
```

**Latest version:** [Releases page](https://github.com/pescheckit/eat-my-sms/releases)

## Configuration

Edit `/etc/eat-my-sms/eat-my-sms.conf`:

```ini
[DEFAULT]
pin = 0000
poll_interval = 5
webhook_url = https://example.com/webhook

# Optional: Enable metrics
# metrics_port = 8080

# Optional: Add extra field to webhook payload
# webhook_extra = production

# Override per device
[ttyUSB0]
poll_interval = 3
webhook_url = https://example.com/other-webhook
```

## Running

**Start a single modem:**
```bash
systemctl start eat-my-sms@ttyUSB0.service
systemctl enable eat-my-sms@ttyUSB0.service
```

**Start ALL modems at once (auto-detect):**
```bash
# Auto-detects all /dev/ttyUSB* devices and starts services
sudo systemctl start eat-my-sms.target
sudo systemctl enable eat-my-sms.target
```

This automatically:
- Scans for devices matching the pattern (default: `ttyUSB*`)
- Starts up to **8 services** by default (configurable)
- Only runs services for ports with working SIM cards

**Configure device detection:**
Edit `/etc/eat-my-sms/devices.conf`:
```bash
MAX_DEVICES=8              # Default: 8 (for 8-way hubs)
DEVICE_PATTERN="ttyUSB*"   # Default: ttyUSB0-7

# Examples for other setups:
# MAX_DEVICES=16           # For 16-way hubs
# DEVICE_PATTERN="ttyACM*" # For direct USB modems
```

**Or start specific modems manually:**
```bash
sudo systemctl start eat-my-sms@ttyUSB0.service
sudo systemctl enable eat-my-sms@ttyUSB0.service
```

**Manage all running modems at once:**
```bash
# These work with globs (only affects already loaded units)
sudo systemctl restart 'eat-my-sms@*.service'
sudo systemctl stop 'eat-my-sms@*.service'
sudo systemctl status 'eat-my-sms@*.service'
```

**Note:** `start` and `enable` don't support globs well - specify each service individually.

## Monitoring

**View logs from all modems:**
```bash
sudo journalctl -u 'eat-my-sms@*' -f
```

**View logs from specific modem:**
```bash
sudo journalctl -u eat-my-sms@ttyUSB0.service -f
```

**Check status of all services:**
```bash
sudo systemctl status 'eat-my-sms@*.service'
```

**Check the target status:**
```bash
sudo systemctl status eat-my-sms.target
```

**Prometheus metrics** (if enabled):
```bash
curl http://localhost:8080/metrics
```

## Troubleshooting

### Check which ports have SIM cards (8-way hub)

```bash
# Test all 8 ports (ttyUSB0 through ttyUSB7)
for i in {0..7}; do
  echo "=== Testing ttyUSB$i ==="
  timeout 10 python3 /usr/share/eat-my-sms/eat-my-sms.py ttyUSB$i 2>&1 | \
    grep -E "unlocked|Network info|timeout|missing"
done
```

**Expected output:**
- Ports with SIM cards: "Network info: T-Mobile..."
- Ports without SIM: "SIM card missing or damaged"

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "SIM card missing or damaged" | No SIM in slot | Check physical SIM card |
| "Timeout" | Modem not responding | Verify baud rate is 115200 |
| "Unknown security code status" | Transitional state | Script handles automatically |
| 404 webhook error | Wrong webhook URL | Update `webhook_url` in config |

### View received SMS in logs

```bash
journalctl -u eat-my-sms@ttyUSB0.service | grep "Received SMS"
```

Example output:
```
[INFO]: Received SMS: from=+31612345678, date=04/03/2026 11:41:21 +0100, body=Test message
```

## PushProx (Prometheus through NAT)

The package includes [PushProx](https://github.com/prometheus-community/PushProx) for monitoring through NAT.

**Configure** `/etc/eat-my-sms/pushprox-client.conf`:
```ini
FQDN=your-hostname.example.com
PROXY_URL=https://pushprox.example.com
```

**Check status:**
```bash
systemctl status pushprox-client.service
```

TLS certificates are auto-generated in `/etc/eat-my-sms/tls/`.

---

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for:
- Building from source
- CI/CD pipeline
- Release process
- Technical architecture
