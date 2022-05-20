# Eat My SMS

A daemon to work with some funky 8-way GSM modem to read SMS messages and send them to a webhook.

## Building Debian package

To build this project as a Debian package, run the following commands on a Debian machine:

```console
# apt install debhelper-compat config-package-dev
$ dpkg-buildpackage -uc -us
```

The `.deb` file will then be created in the parent folder.
To clean the generated files after building the package, run the following command instead:

```console
$ dpkg-buildpackage -uc -us --post-clean
```

By default, the package is built for the architecture of the machine you are building on.
If you want to build for a different architecture, for example `arm64`, use the following command:

```console
$ dpkg-buildpackage -uc -us --host-arch arm64
```

## Installing

Install and run the package with the following commands:

```console
# dpkg -i eat-my-sms.deb
# apt --fix-broken install
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
# systemctl status pushprox-client.service
```

PushProx will use a TLS client certificate to authenticate to the PushProx proxy server running next to Prometheus.
The files are generated upon installation and placed in `/etc/eat-my-sms/tls`.
The `/etc/eat-my-sms/tls/ca.crt` file is the Certificate Authorities' certificate that is used to sign the client certificate.
