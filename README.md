# Eat My SMS

A daemon to work with an 8-way GSM modem hub to read SMS messages and send them to a webhook.

## Features

- 🔄 **Automatic retry logic** with exponential backoff for network registration and SMS reading
- 📦 **Multi-architecture support** (amd64, arm64)
- 🚀 **CI/CD automated builds** with GitLab Package Registry integration
- 📝 **Automatic changelog generation** from git commits
- ⚡ **115200 baud rate** support for modern USB hubs
- 🔧 **Graceful timeout handling** - continues polling on failures instead of crashing
- 📊 **Prometheus metrics** support

## Hardware Support

Tested with:
- 8-way USB GSM modem hubs (Exar XR21V1414 4-channel UART)
- Baud rate: 115200
- Memory: SM (SIM-only) for better reliability

## Quick Start

### Install from GitLab Package Registry

```bash
# Add repository (replace PROJECT_ID with your project ID)
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

### Building Debian package locally

To build this project as a Debian package, run the following commands on a Debian machine:

```console
# Install build dependencies
apt install debhelper-compat config-package-dev python3-pip curl

# Build the package
dpkg-buildpackage -uc -us
```

The `.deb` file will be created in the parent folder.

#### Build for different architecture

```console
dpkg-buildpackage -uc -us --host-arch arm64
```

## Installing from local .deb file

If you built the package locally:

```console
dpkg -i eat-my-sms_*.deb
apt --fix-broken install
```

## Configuration

After installing the package, the [eat-my-sms.conf](eat-my-sms.conf) config file is installed at `/etc/eat-my-sms/eat-my-sms.conf`.
There you can set default configuration values and override them for specific modems.

## Running

To start (and enable) the script for a specific modem, use the `eat-my-sms@<device>.service` systemd unit as the following example:

```console
# systemctl start eat-my-sms@ttyACM0.service
# systemctl enable eat-my-sms@ttyACM0.service

# systemctl start eat-my-sms@ttyACM1.service
...
```

Systemd (after version 209) supports globbing in the template value (as the parameter is called).
Please make sure to add the quotes since your shell might expand the `*` to something else.
And also only use this to restart, stop and disable instances since systemd doesn't know which instances can exist.
This can be done as follows:

```console
# systemctl restart 'eat-my-sms@*.service'
# systemctl stop 'eat-my-sms@*.service'
```

## Metrics

Metrics are tracked and served in Prometheus format on each modem, if enabled.
To enable metrics, set the `metrics_port` value in the main `/etc/eat-my-sms/eat-my-sms.conf` file.

This package ships with a [PushProx](https://github.com/prometheus-community/PushProx) client.
PushProx allows Prometheus to monitor through a NAT.

The PushProx proxy is configured from `/etc/eat-my-sms/pushprox-client.conf`.
Upon installation, a systemd unit file is automatically enabled for PushProx

```console
systemctl status pushprox-client.service
```

PushProx will use a TLS client certificate to authenticate to the PushProx proxy server running next to Prometheus.
The files are generated upon installation and placed in `/etc/eat-my-sms/tls`.
The `/etc/eat-my-sms/tls/ca.crt` file is the Certificate Authorities' certificate that is used to sign the client certificate.

## CI/CD & Release Process

This project uses GitLab CI/CD for automated building and deployment.

### Creating a Release

1. **Make your changes and commit them**
2. **Create a version tag:**
   ```bash
   git tag v0.9.1
   git push origin v0.9.1
   ```

3. **CI/CD automatically:**
   - Generates changelog from commit messages using `gbp dch`
   - Builds packages for amd64 and arm64
   - Tests the amd64 package
   - Uploads to GitLab Package Registry

### Pipeline Stages

- **On commits to master:** Build + Test only
- **On version tags:** Build + Test + Deploy to Package Registry

### Changelog Generation

The Debian changelog is automatically generated from git commit messages when you create a tag:
- Uses `gbp dch` (git-buildpackage)
- Includes all commits since the last tag
- Formats according to Debian standards

## Reliability Improvements

- **Network registration:** 20 retries with exponential backoff (3s → 6s → 12s → 30s max)
- **SMS reading:** 3 retries with exponential backoff (2s → 4s)
- **Timeout handling:** 60 second timeout for gnokii operations
- **Memory type:** Uses SM (SIM-only) instead of MT for better reliability
- **Graceful failures:** Returns empty list on errors, continues polling

## Troubleshooting

### Check which USB ports have SIM cards

```bash
for i in {0..7}; do
  echo "=== Testing ttyUSB$i ==="
  timeout 10 python3 /usr/share/eat-my-sms/eat-my-sms.py ttyUSB$i 2>&1 | grep -E "unlocked|Network info|timeout"
done
```

### View logs

```bash
journalctl -u eat-my-sms@ttyUSB0.service -f
```

### Common Issues

**"SIM card missing or damaged":** No SIM card in that slot
**"Timeout":** Modem not responding - check baud rate (should be 115200)
**"Unknown security code status":** Modem in transitional state - script handles this automatically
