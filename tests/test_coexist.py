#!/usr/bin/env python3
"""Real generated-config interoperability; loopback-only, no ACME/host services."""
import http.server
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'coexist-ok'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args): pass

class RealCoexistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binaries = {'trojan': os.environ['TROJAN_BIN'], 'hysteria2': os.environ['HYSTERIA_BIN']}
        cls.sources = {name: Path(os.environ[key]).read_text() for name, key in
                       [('trojan', 'TROJAN_INSTALLER'), ('hysteria2', 'HYSTERIA_INSTALLER')]}
        locks = {re.search(r'^readonly ACME_LOCK="([^"]+)"', source, re.M).group(1)
                 for source in cls.sources.values()}
        if locks != {'/run/lock/trojan-cert-renew.lock'}:
            raise AssertionError('Installers must use the same legacy-compatible HTTP-01 lock')
        cls.tmp = tempfile.TemporaryDirectory(prefix='mofatizi-real-')
        cls.root = Path(cls.tmp.name)
        cls.target = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.target.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.target.server_port}/coexist'
        for name in ('first', 'renewed'):
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '90',
                            '-subj', '/CN=proxy.example.com', '-addext', 'subjectAltName=DNS:proxy.example.com',
                            '-out', str(cls.root / f'{name}.crt'), '-keyout', str(cls.root / f'{name}.key')],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @classmethod
    def tearDownClass(cls):
        cls.target.shutdown(); cls.target.server_close(); cls.thread.join()
        cls.tmp.cleanup()

    def setUp(self):
        self.case = Path(tempfile.mkdtemp(dir=self.root))
        self.processes = []
        self.handles = []
        self.ports = {}
        self.configs = {}
        self.functions = {}

    def tearDown(self):
        self.stop_processes()
        for handle in self.handles: handle.close()

    def stop_processes(self):
        for p in reversed(self.processes):
            if p.poll() is None: p.terminate()
        for p in reversed(self.processes):
            try: p.wait(timeout=3)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
        self.processes.clear()

    def render(self, protocol, port):
        folder = self.case / protocol
        folder.mkdir(exist_ok=True)
        for ext, target in [('crt', 'cert.pem'), ('key', 'key.pem')]:
            shutil.copyfile(self.root / f'first.{ext}', folder / target)
        source = self.sources[protocol].replace('\nmain "$@"\n', '\n')
        # Trojan already has a source guard. Hysteria's entrypoint is removed above.
        source = re.sub(r'^readonly CONFIG_DIR=.*$', 'readonly CONFIG_DIR=' + shlex.quote(str(folder)), source, flags=re.M)
        source = re.sub(r'^readonly ACME_LOCK=.*$', 'readonly ACME_LOCK=' + shlex.quote(str(self.case / 'shared.lock')), source, flags=re.M)
        fn = folder / 'functions.sh'; fn.write_text(source)
        self.functions[protocol] = fn
        body = 'DOMAIN=proxy.example.com; EMAIL=admin@example.com; PASSWORD=shared-test-password; PORT=' + str(port) + '; '
        if protocol == 'trojan':
            r = subprocess.run(['bash', '-c', 'source "$1"; ' + body + 'render_config', 'test', str(fn)], capture_output=True, text=True, check=True)
            config = json.loads(r.stdout); config['local_addr'] = '127.0.0.1'
            path = folder / 'server.json'; path.write_text(json.dumps(config))
        else:
            subprocess.run(['bash', '-c', 'source "$1"; ' + body + 'NO_MASQUERADE=1; HTTPS_PORT=0; chown() { :; }; write_config', 'test', str(fn)], check=True)
            path = folder / 'config.yaml'
            path.write_text(path.read_text().replace(f'listen: :{port}', f'listen: 127.0.0.1:{port}'))
        self.configs[protocol] = path
        self.ports[protocol] = port

    def launch(self, protocol, config, role):
        log = self.case / (protocol + '-' + role + '-' + str(len(self.processes)) + '.log')
        handle = log.open('w'); self.handles.append(handle)
        cmd = [self.binaries[protocol], '-c', str(config)] if protocol == 'trojan' else [self.binaries[protocol], 'server' if role == 'server' else 'client', '-c', str(config)]
        p = subprocess.Popen(cmd, stdout=handle, stderr=subprocess.STDOUT)
        self.processes.append(p)
        return p, log

    def start_server(self, protocol):
        p, log = self.launch(protocol, self.configs[protocol], 'server')
        for _ in range(100):
            self.assertIsNone(p.poll(), log.read_text())
            if protocol == 'hysteria2':
                if 'server up and running' in log.read_text(): return p
            else:
                try:
                    with socket.create_connection(('127.0.0.1', self.ports[protocol]), timeout=.1): pass
                    return p
                except OSError: pass
            time.sleep(.05)
        self.fail(log.read_text())

    def start_client(self, protocol, trust='first'):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        path = self.case / f'{protocol}-client-{port}.yaml'
        ca = self.root / f'{trust}.crt'
        if protocol == 'trojan':
            config = {'run_type': 'client', 'local_addr': '127.0.0.1', 'local_port': port,
                      'remote_addr': '127.0.0.1', 'remote_port': self.ports[protocol],
                      'password': ['shared-test-password'], 'log_level': 2,
                      'ssl': {'verify': True, 'verify_hostname': True, 'cert': str(ca), 'sni': 'proxy.example.com'}}
            path.write_text(json.dumps(config))
        else:
            path.write_text(f"server: 127.0.0.1:{self.ports[protocol]}\nauth: shared-test-password\ntls:\n  sni: proxy.example.com\n  ca: {ca}\nsocks5:\n  listen: 127.0.0.1:{port}\n")
        p, log = self.launch(protocol, path, 'client')
        for _ in range(100):
            self.assertIsNone(p.poll(), log.read_text())
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.1): pass
                return port
            except OSError: time.sleep(.05)
        self.fail(log.read_text())

    def request(self, port):
        r = subprocess.run(['curl', '-q', '-fsS', '--noproxy', '', '--socks5-hostname', f'127.0.0.1:{port}',
                            '--connect-timeout', '3', '--max-time', '5', self.url], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, 'coexist-ok')

    def test_both_orders_default_same_number_and_custom_ports(self):
        ports = [(443, 443), (443, 8443), (8443, 443), (19443, 19444)]
        if os.environ.get('COEXIST_TEST_HIGH_PORTS') == '1':
            print('NOTE: high-port-only local run; CI must also test real TCP/UDP 443.')
            ports = [(8443, 8443), (8443, 19443), (19443, 8443), (19443, 19444)]
        for tcp, udp in ports:
            for order in [('trojan', 'hysteria2'), ('hysteria2', 'trojan')]:
                with self.subTest(tcp=tcp, udp=udp, order=order):
                    self.render('trojan', tcp); self.render('hysteria2', udp)
                    try:
                        first = self.start_server(order[0])
                        first_client = self.start_client(order[0]); self.request(first_client)
                        second = self.start_server(order[1])
                        second_client = self.start_client(order[1]); self.request(second_client)
                        self.assertIsNone(first.poll())
                        self.request(first_client)
                        self.assertIsNone(second.poll())
                    finally:
                        self.stop_processes()

    def test_hysteria_new_certificate_without_restart_and_trojan_unchanged(self):
        self.render('trojan', 19443); self.render('hysteria2', 19444)
        t = self.start_server('trojan'); h = self.start_server('hysteria2')
        tc = self.start_client('trojan'); old_hc = self.start_client('hysteria2')
        self.request(tc); self.request(old_hc)
        for ext, target in [('key', 'key.pem'), ('crt', 'cert.pem')]:
            shutil.copyfile(self.root / f'renewed.{ext}', self.case / 'hysteria2' / target)
        new_hc = self.start_client('hysteria2', trust='renewed')
        self.request(new_hc); self.request(old_hc); self.request(tc)
        self.assertIsNone(t.poll()); self.assertIsNone(h.poll())

    def test_installation_certificate_operations_are_serialized(self):
        self.render('trojan', 443); self.render('hysteria2', 443)
        events = self.case / 'lock-events'
        processes = []
        for protocol in ('trojan', 'hysteria2'):
            body = '''source "$1"
cert_valid() { return 1; }
# Positional args are passed explicitly to the callback through wrapper globals.
NAME="$2"; EVENTS="$3"
obtain_certificate_locked() { echo "enter $NAME" >> "$EVENTS"; sleep 0.15; echo "exit $NAME" >> "$EVENTS"; }
obtain_certificate
'''
            p = subprocess.Popen(['bash', '-c', body, 'test', str(self.functions[protocol]), protocol, str(events)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            processes.append(p)
        for p in processes:
            out, err = p.communicate(timeout=5)
            self.assertEqual(p.returncode, 0, out + err)
        lines = events.read_text().splitlines()
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith('enter '))
        self.assertEqual(lines[1], lines[0].replace('enter ', 'exit '))
        self.assertEqual(lines[3], lines[2].replace('enter ', 'exit '))

if __name__ == '__main__':
    unittest.main(verbosity=2)
