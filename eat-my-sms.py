#!/usr/bin/env python3

import argparse
import configparser
import json
import logging
import os
import re
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

import serial
from prometheus_client import start_wsgi_server, Counter, REGISTRY

CONFIG = {}
GNOKII_CONFIG_TEMPLATE = '''
[global]
port = /dev/{}
model = AT
connection = serial
serial_baudrate = 115200
'''
DEFAULT_SMS_STORAGE = 'MT'
PROM_RECEIVED_SMS = None
PROM_WEBHOOK_FAILED = None


def read_config(path, device):
    cfg = configparser.ConfigParser()
    cfg.read(path)

    # If section device does not exist in the config, we need to add it here,
    # otherwise the get method is going to throw an error
    if not cfg.has_section(device):
        cfg.add_section(device)

    CONFIG['port'] = device
    CONFIG['pin'] = cfg.get(device, 'pin')
    CONFIG['poll_interval'] = int(cfg.get(device, 'poll_interval'))
    CONFIG['webhook_url'] = cfg.get(device, 'webhook_url')
    CONFIG['webhook_extra'] = cfg.get(device, 'webhook_extra', fallback=None)
    CONFIG['metrics_port'] = cfg.get(device, 'metrics_port', fallback=None)
    CONFIG['sms_storage'] = cfg.get(device, 'sms_storage', fallback=DEFAULT_SMS_STORAGE)


def send_message(message):
    if CONFIG['webhook_extra']:
        message['extra'] = CONFIG['webhook_extra']
    message['port'] = CONFIG['port']

    req = urllib.request.Request(CONFIG['webhook_url'])
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    req.add_header('User-Agent', 'EatMySMS/1.0')
    try:
        urllib.request.urlopen(req, json.dumps(message).encode('utf-8'))
    except urllib.error.URLError as err:
        logging.error('Could not send message: {}'.format(message))
        logging.exception(err)
        PROM_WEBHOOK_FAILED.labels(
            CONFIG['port'], CONFIG['webhook_extra'], CONFIG['webhook_url']).inc()


class Modem:
    def __init__(self, port):
        logging.info('Initializing modem at /dev/{}'.format(port))
        self.port = port

        # Deterministic per-port path so restarts overwrite instead of leaking
        # a new file per process start (see 873k-orphan /tmp incident).
        config_dir = os.environ.get('RUNTIME_DIRECTORY', tempfile.gettempdir())
        self.config = os.path.join(config_dir, 'gnokii-{}.conf'.format(port))
        with open(self.config, 'w') as config:
            config.write(GNOKII_CONFIG_TEMPLATE.format(port))
        logging.info('Wrote gnokii config to: {}'.format(self.config))

        # Check if a pin needs to be entered and do so
        logging.info('Checking if SIM is locked...')
        if self.is_locked():
            logging.info('SIM is locked, entering PIN...')
            self.enter_pin()
            if self.is_locked():
                raise Exception('SIM still not unlocked after entering pin')
        else:
            logging.info('SIM is unlocked')

        # Wait until connected to network, then print info
        max_retries = 20
        retry_delay = 3
        for attempt in range(max_retries):
            info = self.network_info()
            if re.match(r'undefined', info['Network code'], re.I):
                if attempt < max_retries - 1:
                    logging.info('Not connected to network yet (attempt {}/{}), waiting {}s...'.format(
                        attempt + 1, max_retries, retry_delay))
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30)  # Exponential backoff, max 30s
                else:
                    raise Exception('Failed to connect to network after {} attempts'.format(max_retries))
            else:
                break
        logging.info('Network info: {}'.format(info))

        # Pick a storage that matches where the modem actually puts incoming
        # SMS. Default MT reads ME+SIM combined, which works regardless of the
        # modem's factory default (e.g. Quectel EC25 stores in ME, older modems
        # often default to SM). SM/ME force a specific storage via AT+CPMS.
        self.set_sms_storage(CONFIG['sms_storage'])

        logging.info('Modem at /dev/{} initialized'.format(port))

    def command(self, *args, input=None):
        stdin = None
        if input:
            input = input.encode()
            stdin = subprocess.PIPE

        with subprocess.Popen(
            ['gnokii', '--config', self.config, *args],
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        ) as process:
            try:
                stdout, stderr = process.communicate(input, timeout=60)
            except subprocess.TimeoutExpired:
                logging.warning(
                    "Gnokii command timed out after 60s, killing process...")
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                raise  # Re-raise to allow retry logic to catch it
            except Exception as e:
                logging.error("Gnokii command failed: {}".format(e))
                raise

        stdout = stdout.decode('utf-8')
        stderr = stderr.decode('utf-8')

        err = re.search(r'^error:(.*)$', stderr, re.M | re.I)
        if err:
            raise Exception('Error from gnokii', err.group(1).strip())

        return (stdout, stderr)

    def is_locked(self):
        cmd = self.command('--getsecuritycodestatus')

        status = re.search(r'^security code status:(.*)$', cmd[0], re.M | re.I)
        if status:
            msg = status.group(1).strip()
            if re.search(r'waiting for pin', msg, re.I):
                return True
            if re.search(r'nothing to enter', msg, re.I):
                return False
            if re.search(r'unknown', msg, re.I):
                logging.warning('Security code status is unknown, assuming unlocked')
                return False
            else:
                raise Exception('Invalid security code status', msg)
        else:
            raise Exception('Could not read security code status')

    def enter_pin(self):
        cmd = self.command('--entersecuritycode', 'PIN', input=CONFIG['pin'])

        status = re.search(r'^code ok', cmd[1], re.M | re.I)
        if status:
            logging.info('PIN accepted, SIM unlocked')
        else:
            raise Exception('PIN was not accepted', cmd[1])

    def network_info(self):
        cmd = self.command('--getnetworkinfo')

        info = {}
        for line in cmd[0].strip().split('\n'):
            match = re.match('^(.*):(.*)$', line)
            if match:
                info[match.group(1).strip()] = match.group(2).strip()
        return info

    def set_sms_storage(self, storage):
        # MT is the combined ME+SIM view. Setting +CPMS mem3 (incoming) to MT is
        # not portable — many modems only accept SM or ME for incoming storage.
        # Since reads via MT span both, we leave incoming storage at the modem's
        # default and only need to act for explicit SM/ME pins.
        if storage == 'MT':
            logging.info('SMS storage: MT (read from combined ME+SIM, no +CPMS override)')
            return

        # AT+CPMS=<mem1>,<mem2>,<mem3> — read/delete, send/write, receive
        at = 'AT+CPMS="{0}","{0}","{0}"\r'.format(storage)
        try:
            with serial.Serial('/dev/{}'.format(self.port), 115200, timeout=2) as s:
                s.reset_input_buffer()
                s.write(at.encode())
                resp = s.read(256).decode(errors='replace')
        except serial.SerialException as e:
            raise Exception('Could not open serial port to set SMS storage', str(e))

        if 'OK' not in resp:
            raise Exception('Modem rejected AT+CPMS', resp.strip())
        logging.info('SMS storage set to {}'.format(storage))

    def read_sms(self):
        # Storage configured at init via AT+CPMS — see Modem.set_sms_storage
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                cmd = self.command('--getsms', CONFIG['sms_storage'], '1', 'end', '--delete')
                break  # Success, exit retry loop
            except subprocess.TimeoutExpired:
                if attempt < max_retries - 1:
                    logging.warning('SMS read timeout (attempt {}/{}), retrying in {}s...'.format(
                        attempt + 1, max_retries, retry_delay))
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logging.error('SMS read failed after {} attempts, skipping this poll cycle'.format(max_retries))
                    return []  # Return empty list, continue polling
            except Exception as e:
                logging.error('SMS read error: {}'.format(e))
                return []  # Return empty list on other errors

        sms = []
        messages = re.split(
            r'\d+\. inbox message.*[\n]', cmd[0], flags=re.M | re.I)
        for msg in messages:
            if msg:
                PROM_RECEIVED_SMS.labels(
                    CONFIG['port'], CONFIG['webhook_extra'], CONFIG['webhook_url']).inc()
                data = {}

                date = re.search(r'^date/time:(.*)$', msg, re.M | re.I)
                if date:
                    data['date'] = date.group(1).strip()
                sender = re.search(r'^sender:\s+(\+\d+)', msg, re.M | re.I)
                if sender:
                    data['sender'] = sender.group(1).strip()
                smsc = re.search(r'msg center:\s+(\+\d+)', msg, re.M | re.I)
                if smsc:
                    data['smsc'] = smsc.group(1).strip()

                body_parts = re.split(r'^text:[\n]', msg, flags=re.M | re.I)
                if len(body_parts) > 1:
                    data['body'] = body_parts[1].strip()
                else:
                    data['body'] = ''

                sms.append(data)

        return sms


def main():
    logging.basicConfig(
        format='%(asctime)s [%(levelname)s]: %(message)s', level=logging.INFO)

    parser = argparse.ArgumentParser(description='SMS reader')
    parser.add_argument('port', metavar='PORT', type=str,
                        help='Device name to communicate with (ex. ttyACM0, see `ls /dev/ttyACM*`)')
    parser.add_argument(
        '--config', type=str, default='/etc/eat-my-sms/eat-my-sms.conf', help='Config file to use')
    args = parser.parse_args()

    read_config(args.config, args.port)
    modem = Modem(args.port)

    # Disable all default collectors
    for coll in list(REGISTRY._collector_to_names.keys()):
        REGISTRY.unregister(coll)

    # Register new collectors
    global PROM_RECEIVED_SMS, PROM_WEBHOOK_FAILED
    PROM_RECEIVED_SMS = Counter('eatmysms_sms_received_total', 'Number of SMSes received', [
                                'port', 'extra', 'webhook_url'])
    PROM_RECEIVED_SMS.labels(
        args.port, CONFIG['webhook_extra'], CONFIG['webhook_url'])
    PROM_WEBHOOK_FAILED = Counter('eatmysms_webhook_failed_total', 'Number of webhook call failures', [
                                  'port', 'extra', 'webhook_url'])
    PROM_WEBHOOK_FAILED.labels(
        args.port, CONFIG['webhook_extra'], CONFIG['webhook_url'])

    if CONFIG['metrics_port']:
        logging.info('Starting metrics server at 127.0.0.1:{}'.format(
            CONFIG['metrics_port']))
        start_wsgi_server(int(CONFIG['metrics_port']), '127.0.0.1')

    logging.info('Start reading SMS...')
    while True:
        for sms in modem.read_sms():
            logging.info('Received SMS: from={}, date={}, body={}'.format(
                sms.get('sender', 'unknown'), sms.get('date', 'unknown'), sms.get('body', '')))
            send_message(sms)
        time.sleep(CONFIG['poll_interval'])


if __name__ == '__main__':
    main()
