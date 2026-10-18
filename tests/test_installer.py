#!/usr/bin/env python3
"""Exercise menu, preservation, argument dispatch and fail-closed downloads."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.events = self.root / 'events'
        self.configs = {p: self.root / (p + '.conf') for p in ('trojan', 'hysteria2')}
        self.source = (ROOT / 'install.sh').read_text()
        self.source = self.source.replace('/etc/trojan/server.json', str(self.configs['trojan']))
        self.source = self.source.replace('/etc/hysteria/config.yaml', str(self.configs['hysteria2']))
        self.source = self.source.replace('/run/lock/mofatizi-installer.lock', str(self.root / 'lock'))
        self.source = self.source.replace('[[ "$EUID" == 0 ]]', 'true')
        self.script = self.root / 'install.sh'
        self.script.write_text(self.source)
        self.mock = r'''
download_installer() {
  echo "download $1" >> "$EVENTS"
  [[ "${FAIL_DOWNLOAD:-}" != "$1" ]] || die 'download rejected'
  printf 'protocol=%q\n' "$1" > "$2"
  cat >> "$2" <<'CHILD'
set -e
printf 'run %s' "$protocol" >> "$EVENTS"
printf ' %s' "$@" >> "$EVENTS"
printf '\n' >> "$EVENTS"
if [[ " $* " == *' --password-stdin '* ]]; then
  IFS= read -r password
  printf 'password %s %s\n' "$protocol" "$password" >> "$EVENTS"
fi
[[ "${FAIL_CHILD:-}" != "$protocol" ]]
CHILD
}
'''
        self.args = ['all', '--domain', 'proxy.example.com', '--email', 'admin@example.com']

    def run_script(self, args=None, body=None, ok=True, input=None, **env):
        args = self.args if args is None else args
        if body is None:
            body = self.mock + '\nmain "$@"'
        r = subprocess.run(['bash', '-c', 'source "$1"; shift; ' + body, 'test', str(self.script), *args],
                           env=dict(os.environ, EVENTS=str(self.events), **env), input=input, text=True, capture_output=True, timeout=10)
        self.assertEqual(r.returncode == 0, ok, r.stdout + r.stderr)
        return r

    def events_text(self):
        return self.events.read_text() if self.events.exists() else ''

    def test_all_passes_distinct_ports_domains_and_sequential_order(self):
        self.run_script(self.args + ['--trojan-port', '443', '--hysteria2-port', '8443', '--hysteria2-domain', 'hy2.example.com'])
        lines = self.events_text().splitlines()
        self.assertEqual(lines[:2], ['download trojan', 'download hysteria2'])
        self.assertIn('run trojan install --domain proxy.example.com --email admin@example.com --port 443', lines[2])
        self.assertIn('run hysteria2 install --domain hy2.example.com --email admin@example.com --port 8443', lines[3])

    def test_existing_protocol_preserved_in_both_orders(self):
        for existing, missing in [('trojan', 'hysteria2'), ('hysteria2', 'trojan')]:
            with self.subTest(existing=existing):
                for p in self.configs.values(): p.unlink(missing_ok=True)
                self.events.unlink(missing_ok=True)
                self.configs[existing].write_text('existing-domain/password/port')
                r = self.run_script()
                self.assertIn(f'SKIP {existing}', r.stdout)
                self.assertNotIn(f'run {existing}', self.events_text())
                self.assertIn(f'run {missing}', self.events_text())
                self.assertEqual(self.configs[existing].read_text(), 'existing-domain/password/port')

    def test_webroot_default_and_override_are_passed_to_children(self):
        common = self.root / 'website'
        hy2 = self.root / 'second site'
        common.mkdir()
        hy2.mkdir()
        self.run_script(self.args + ['--acme-webroot', str(common), '--hysteria2-acme-webroot', str(hy2)])
        lines = self.events_text().splitlines()
        self.assertIn('--acme-webroot ' + str(common), next(x for x in lines if x.startswith('run trojan')))
        self.assertIn('--acme-webroot ' + str(hy2), next(x for x in lines if x.startswith('run hysteria2')))

    def test_recover_only_failed_hy2_preserves_existing_trojan(self):
        self.configs['trojan'].write_text('legacy-config')
        self.configs['hysteria2'].write_text('official-sample-after-failure')
        r = self.run_script(['hysteria2'])
        self.assertIn('--reinstall', r.stdout)
        self.assertEqual(self.events_text(), '')
        self.run_script(['hysteria2', '--domain', 'hy2.example.com', '--email', 'admin@example.com',
                         '--port', '8443', '--reinstall', '--yes'])
        self.assertIn('run hysteria2', self.events_text())
        self.assertNotIn('run trojan', self.events_text())
        self.assertEqual(self.configs['trojan'].read_text(), 'legacy-config')

    def test_yes_alone_does_not_replace_existing_and_no_identity_needed_when_all_installed(self):
        for path in self.configs.values(): path.write_text('keep')
        self.run_script(['all', '--yes'])
        self.assertEqual(self.events_text(), '')
        self.run_script(self.args + ['--reinstall', '--yes'])
        self.assertIn('--yes', self.events_text())
        self.assertIn('run trojan', self.events_text())
        self.assertIn('run hysteria2', self.events_text())

    def test_menu_maps_all_three_choices(self):
        for choice, expected in [('1', 'all'), ('2', 'trojan'), ('3', 'hysteria2')]:
            self.run_script([], body='prompt() { printf -v "$1" %s "$CHOICE"; }; choose_protocol; [[ "$TARGET" == "$EXPECTED" ]]', CHOICE=choice, EXPECTED=expected)
        self.run_script([], body='prompt() { printf -v "$1" %s 4; }; choose_protocol', ok=False)

    def test_dry_run_has_no_downloads_or_mutations(self):
        self.run_script(self.args + ['--dry-run'])
        self.assertFalse(self.events.exists())
        self.assertFalse((self.root / 'lock').exists())

    def test_stdin_password_preserved_without_password_in_arguments(self):
        args = ['trojan', '--domain', 'proxy.example.com', '--email', 'admin@example.com', '--port', '8443', '--password-stdin']
        secret = 'original-password_123'
        r = self.run_script(args, input=secret + '\n')
        lines = self.events_text().splitlines()
        self.assertNotIn(secret, r.stdout + r.stderr)
        self.assertNotIn(secret, next(x for x in lines if x.startswith('run ')))
        self.assertIn('password trojan ' + secret, lines)
        self.run_script(args, ok=False, input='\n')

    def test_distinct_password_files_for_all(self):
        files = {}
        for protocol in self.configs:
            path = self.root / (protocol + '.password')
            path.write_text(protocol + '-old-password\n')
            files[protocol] = str(path)
        self.run_script(self.args + ['--trojan-password-file', files['trojan'], '--hysteria2-password-file', files['hysteria2']])
        for protocol in files:
            self.assertIn(f'password {protocol} {protocol}-old-password', self.events_text())

    def test_invalid_parameters_stop_before_any_download(self):
        for extra in [['--port', '8443'], ['--password-stdin'], ['--trojan-port', '80'], ['--hysteria2-port', '0'],
                      ['--hysteria2-https-port', '443'], ['--hysteria2-https-port', '80'], ['--unknown'],
                      ['--acme-webroot', 'relative/path'], ['--acme-webroot', str(self.root / 'absent')],
                      ['--trojan-domain', 'bad;domain'], ['--hysteria2-version', 'v1.0.0']]:
            with self.subTest(extra=extra):
                self.run_script(self.args + extra, ok=False)
                self.assertFalse(self.events.exists())

    def test_all_downloads_checked_before_first_install(self):
        self.run_script(ok=False, FAIL_DOWNLOAD='hysteria2')
        self.assertNotIn('run ', self.events_text())

    def test_partial_failure_returns_nonzero_and_retains_first_service(self):
        r = self.run_script(ok=False, FAIL_CHILD='hysteria2')
        self.assertIn('Completed: trojan', r.stderr)
        self.assertIn('retry only hysteria2 with --reinstall', r.stderr)
        self.assertEqual(self.events_text().count('run trojan'), 1)
        self.assertNotIn('uninstall', self.events_text())

    def test_real_checksum_verification_rejects_corruption(self):
        payload = self.root / 'payload'
        payload.write_text('#!/bin/bash\necho safe\n')
        digest = hashlib.sha256(payload.read_bytes()).hexdigest()
        import re
        source = re.sub(r'declare -Ar REVISIONS=.*', 'declare -Ar REVISIONS=([trojan]=' + 'a'*40 + ' [hysteria2]=' + 'a'*40 + ')', self.source)
        source = re.sub(r'declare -Ar CHECKSUMS=.*', f'declare -Ar CHECKSUMS=([trojan]={digest} [hysteria2]={digest})', source)
        self.script.write_text(source)
        body = 'curl() { cp "$PAYLOAD" "${@: -1}"; }; download_installer trojan "$DEST"'
        self.run_script([], body=body, PAYLOAD=str(payload), DEST=str(self.root / 'download'))
        payload.write_text('#!/bin/bash\necho altered\n')
        self.run_script([], body=body, ok=False, PAYLOAD=str(payload), DEST=str(self.root / 'download'))

if __name__ == '__main__':
    unittest.main(verbosity=2)
