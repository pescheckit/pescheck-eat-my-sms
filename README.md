# Eat My SMS

A daemon to work with 8-way GSM modem hubs to read SMS messages and send them to a webhook.

## Features

- 🔄 Automatic retry logic with exponential backoff
- ⚡ 115200 baud rate support for modern USB hubs
- 🔧 Graceful error handling - continues on failures
- 📊 Prometheus metrics support
- 📦 Multi-architecture packages (amd64, arm64)

## Hardware Support

Tested with:
- 8-way USB GSM modem hubs (Exar XR21V1414)
- Baud rate: 115200
- Device names: `ttyUSB0-7` (USB hubs) or `ttyACM0-X` (direct USB modems)

## Installation

### From GitLab Package Registry

```bash
# Add repository
echo "deb https://gitlab.pescheck.me/api/v4/projects/3/packages/debian stable main" | \
  sudo tee /etc/apt/sources.list.d/eat-my-sms.list

# Configure authentication
sudo tee /etc/apt/auth.conf.d/gitlab.conf > /dev/null <<EOF
machine gitlab.pescheck.me
login <your-username>
password <your-personal-access-token>
EOF
sudo chmod 600 /etc/apt/auth.conf.d/gitlab.conf

# Install
sudo apt update
sudo apt install eat-my-sms
```

### From local .deb file

```bash
dpkg -i eat-my-sms_*.deb
apt --fix-broken install
```

## Configuration

Edit `/etc/eat-my-sms/eat-my-sms.conf`:

```ini
[DEFAULT]
pin = 0000
poll_interval = 5
webhook_url = https://dashboard.pescheck.io/webhook/vog

# Optional: Enable metrics
# metrics_port = 8080

# Optional: Add extra field to webhook payload
# webhook_extra = production

# Override per device
[ttyUSB0]
poll_interval = 3
webhook_url = https://different-webhook.example.com
```

## Running

**Start a single modem:**
```bash
systemctl start eat-my-sms@ttyUSB0.service
systemctl enable eat-my-sms@ttyUSB0.service
```

**Start multiple modems:**
```bash
systemctl start eat-my-sms@ttyUSB{0,1,3}.service
systemctl enable eat-my-sms@ttyUSB{0,1,3}.service
```

**Manage all modems:**
```bash
systemctl restart 'eat-my-sms@*.service'
systemctl stop 'eat-my-sms@*.service'
```

## Monitoring

**View logs:**
```bash
journalctl -u eat-my-sms@ttyUSB0.service -f
```

**Check status:**
```bash
systemctl status eat-my-sms@ttyUSB0.service
```

**Prometheus metrics** (if enabled):
```bash
curl http://localhost:8080/metrics
```

## Troubleshooting

### Check which ports have SIM cards

```bash
for i in {0..7}; do
  echo "=== Testing ttyUSB$i ==="
  timeout 10 python3 /usr/share/eat-my-sms/eat-my-sms.py ttyUSB$i 2>&1 | \
    grep -E "unlocked|Network info|timeout|missing"
done
```

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
