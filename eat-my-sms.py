#!/usr/bin/env python3

import argparse
import configparser
import json
import logging
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

CONFIG = {}
GNOKII_CONFIG_TEMPLATE = '''
[global]
port = /dev/{}
model = AT
connection = serial
serial_baudrate = 57600
'''

def read_config(path, device):
    cfg = configparser.ConfigParser()
    cfg.read(path)

    # If section device does not exist in the config, we need to add it here,
    # otherwise the get method is going to throw an error
    if not cfg.has_section(device):
        cfg.add_section(device)

    CONFIG['pin'] = cfg.get(device, 'pin')
    CONFIG['poll_interval'] = int(cfg.get(device, 'poll_interval'))
    CONFIG['webhook_url'] = cfg.get(device, 'webhook_url')
    CONFIG['webhook_extra'] = cfg.get(device, 'webhook_extra', fallback=None)

def send_message(message):
    if CONFIG['webhook_extra']:
        message['extra'] = CONFIG['webhook_extra']

    req = urllib.request.Request(CONFIG['webhook_url'])
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    try:
        urllib.request.urlopen(req, json.dumps(message).encode('utf-8'))
    except urllib.error.URLError as err:
        logging.error('Could not send message: {}'.format(message))
        logging.exception(err)

class Modem:
    def __init__(self, port):
        logging.info('Initializing modem at /dev/{}'.format(port))

        with tempfile.NamedTemporaryFile(mode='w+t', prefix='gnokii-', delete=False) as config:
            config.write(GNOKII_CONFIG_TEMPLATE.format(port))
            self.config = config.name
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
        while True:
            info = self.network_info()
            if re.match(r'undefined', info['Network code'], re.I):
                logging.info('Not connected to network yet, waiting to try again...')
                time.sleep(3)
            else:
                break
        logging.info('Network info: {}'.format(info))

        logging.info('Modem at /dev/{} initialized'.format(port))

    def command(self, *args, input=None):
        if input:
            input = input.encode()

        cmd = subprocess.run(
            ['gnokii', '--config', self.config, *args],
            input=input,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        stdout = cmd.stdout.decode('utf-8')
        stderr = cmd.stderr.decode('utf-8')

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

    def read_sms(self):
        cmd = self.command('--getsms', 'MT', '1', 'end', '--delete')

        sms = []
        messages = re.split(r'\d+\. inbox message.*[\n]', cmd[0], flags=re.M | re.I)
        for msg in messages:
            if msg:
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
                data['body'] = re.split(r'^text:[\n]', msg, flags=re.M | re.I)[1].strip()
                
                sms.append(data)

        return sms

def main():
    logging.basicConfig(format='%(asctime)s [%(levelname)s]: %(message)s', level=logging.INFO)

    parser = argparse.ArgumentParser(description='SMS reader')
    parser.add_argument('port', metavar='PORT', type=str, help='Device name to communicate with (ex. ttyACM0, see `ls /dev/ttyACM*`)')
    parser.add_argument('--config', type=str, default='/etc/eat-my-sms/eat-my-sms.conf', help='Config file to use')
    args = parser.parse_args()

    read_config(args.config, args.port)
    modem = Modem(args.port)

    logging.info('Start reading SMS...')
    while True:
        for sms in modem.read_sms():
            send_message(sms)
        time.sleep(CONFIG['poll_interval'])

if __name__ == '__main__':
    main()
