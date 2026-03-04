# Development Guide

## Building from Source

### Prerequisites

```bash
apt install debhelper-compat config-package-dev python3-pip curl git-buildpackage
```

### Build Package

```bash
# Build for current architecture
dpkg-buildpackage -uc -us

# Build for specific architecture
dpkg-buildpackage -uc -us --host-arch arm64

# Clean build artifacts
dpkg-buildpackage -uc -us --post-clean
```

The `.deb` file will be created in the parent directory.

## CI/CD Pipeline

This project uses **GitHub Actions** for automated building and deployment.

### Workflows

**On commits to master/main (build-test.yml):**
1. **Build** - Builds packages for amd64 and arm64
2. **Test** - Tests amd64 package installation

**On version tags (release.yml):**
1. **Build** - Builds packages + auto-generates changelog with `gbp dch`
2. **Test** - Tests amd64 package installation
3. **Release** - Creates GitHub Release with .deb attachments

### Creating a Release

1. **Make your changes and commit:**
   ```bash
   git add .
   git commit -m "Your changes"
   git push origin master
   ```

2. **Create and push a version tag:**
   ```bash
   git tag v0.9.1
   git push origin v0.9.1
   ```

3. **GitHub Actions automatically:**
   - Generates Debian changelog from all commits since last tag using `gbp dch`
   - Builds `.deb` packages for amd64 and arm64
   - Tests package installation
   - Creates GitHub Release with packages attached

### Changelog Generation

The Debian changelog is **automatically generated** from git commit messages:

- Uses `gbp dch` (git-buildpackage)
- Extracts all commits between the previous tag and current tag
- Formats according to Debian standards
- Version is extracted from git tag (strips `v` prefix)

**Example:**
```bash
# Your commits:
git commit -m "Fix timeout handling"
git commit -m "Add retry logic for SMS reading"
git commit -m "Update webhook URL format"

# Create tag:
git tag v0.9.1

# Generated changelog will include all 3 commits
```

**Supported tag formats:**
- `v0.9.1` → version `0.9.1`
- `0.9.1` → version `0.9.1`
- `v1.0.0-beta` → version `1.0.0-beta`

## Technical Architecture

### Reliability Features

**Network Registration:**
- 20 retries with exponential backoff
- Delay: 3s → 6s → 12s → 24s → 30s (max)
- Timeout: 60 seconds per operation

**SMS Reading:**
- 3 retries with exponential backoff
- Delay: 2s → 4s
- Timeout: 60 seconds per gnokii operation
- Memory: SM (SIM-only) instead of MT for better reliability

**Error Handling:**
- Graceful timeout handling - logs error and continues
- Returns empty list on failures instead of crashing
- Handles "unknown" security code status automatically

### Communication Flow

```
┌─────────────┐      ┌──────────┐      ┌─────────────┐
│  GSM Modem  │ ←──→ │  gnokii  │ ←──→ │ eat-my-sms  │
│ (ttyUSB0)   │ AT   │   CLI    │ API  │   daemon    │
└─────────────┘      └──────────┘      └─────────────┘
                                              │
                                              ↓ HTTP POST
                                        ┌──────────────┐
                                        │   Webhook    │
                                        │   Endpoint   │
                                        └──────────────┘
```

### Configuration Hierarchy

1. **DEFAULT section** in `/etc/eat-my-sms/eat-my-sms.conf`
2. **Device-specific section** (e.g., `[ttyUSB0]`)
3. **Command-line arguments** (via systemd service)

Device-specific settings override defaults.

### Baud Rate Changes

**Why 115200?**
- Modern USB hubs (Exar XR21V1414) operate at 115200 baud
- Previous default was 57600 for older hardware
- Changed in `eat-my-sms.py` line 23

**gnokii Configuration:**
```ini
[global]
port = /dev/ttyUSB0
model = AT
connection = serial
serial_baudrate = 115200
```

### Memory Type: SM vs MT

**SM (SIM Memory):**
- Direct SIM card storage
- More reliable, faster
- Used by this daemon

**MT (Mobile Terminal + SIM):**
- Combined phone and SIM storage
- Slower, more prone to timeouts
- Not recommended

## GitHub Releases

### Package Distribution

Packages are distributed via **GitHub Releases** (publicly accessible):
```
https://github.com/YOUR-USERNAME/eat-my-sms/releases
```

**Package naming:** `eat-my-sms_{version}_{arch}.deb`
**Architectures:** `amd64`, `arm64`

### Authentication

Uses `GITHUB_TOKEN` for automatic authentication in GitHub Actions (predefined secret, no setup needed).

### Download Packages

```bash
# Public download (no authentication needed for public repos)
VERSION="1.0.3"
ARCH="amd64"

wget https://github.com/YOUR-USERNAME/eat-my-sms/releases/download/v${VERSION}/eat-my-sms_${VERSION}_${ARCH}.deb

# Or with curl
curl -L -O https://github.com/YOUR-USERNAME/eat-my-sms/releases/download/v${VERSION}/eat-my-sms_${VERSION}_${ARCH}.deb
```

## Testing

### Manual Testing

```bash
# Build and install locally
dpkg-buildpackage -uc -us
sudo dpkg -i ../eat-my-sms_*.deb
sudo apt --fix-broken install

# Test with a single modem
sudo systemctl start eat-my-sms@ttyUSB0.service
sudo journalctl -u eat-my-sms@ttyUSB0.service -f

# Send test SMS to the modem and verify webhook receives it
```

### CI/CD Testing

The pipeline automatically:
1. Builds the package in a clean Debian container
2. Installs the package
3. Verifies dependencies are correct
4. Checks systemd units are installed

## Project Structure

```
eat-my-sms/
├── eat-my-sms.py              # Main daemon
├── eat-my-sms.conf            # Default configuration
├── pushprox-client.conf       # PushProx configuration
├── requirements.txt           # Python dependencies
├── debian/                    # Debian packaging
│   ├── changelog             # Auto-generated by gbp dch
│   ├── control               # Package metadata
│   ├── install               # File installation rules
│   ├── rules                 # Build rules
│   ├── *.service             # Systemd units
│   └── ...
├── .gitlab-ci.yml            # CI/CD pipeline
├── README.md                 # User documentation
└── DEVELOPMENT.md            # This file
```

## Debugging

### Enable verbose gnokii logging

Modify `/tmp/gnokii-*` config (created by daemon):
```ini
[logging]
debug = on
rlpdebug = on
xdebug = on
```

### Check gnokii directly

```bash
# Create test config
cat > /tmp/test-gnokii.conf <<EOF
[global]
port = /dev/ttyUSB0
model = AT
connection = serial
serial_baudrate = 115200
EOF

# Test communication
gnokii --config /tmp/test-gnokii.conf --identify
gnokii --config /tmp/test-gnokii.conf --getsms SM 1 end
```

### Common Development Issues

**Issue:** `gbp dch` fails with "Currently not on a branch"
**Solution:** Pipeline creates temporary branch automatically

**Issue:** `grep -P` not found in deploy stage
**Solution:** Fixed - using `sed -E` for BusyBox compatibility

**Issue:** Conffile path duplication
**Solution:** Removed manual `debian/conffiles` - auto-generated now

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test locally
5. Push and create a merge request
6. CI/CD will automatically build and test
7. After merge, create a tag for release
