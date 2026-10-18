# mofatizi-installer

[English](README.md) | [简体中文](README.zh-CN.md)

One entry point for [Trojan](https://github.com/sxmad/trojan-installer) and [Hysteria 2](https://github.com/sxmad/hysteria2-installer), with an interactive menu or direct parameters. Revision **2026-10-18.2**. Default documentation and static page metadata are English.

## Interactive menu

```bash
sudo bash -c 'bash <(curl -fsSL --proto "=https" --tlsv1.2 \
  https://raw.githubusercontent.com/sxmad/mofatizi-installer/main/install.sh)'
```

```text
1: all
2: trojan
3: hysteria2
Select:
```

The script asks for missing domain/email values. `all` installs missing protocols sequentially. Existing configurations are **preserved and skipped**, including their passwords and ports; no service is stopped just to make room for another protocol. Skipping is not a health check of the existing service.

## Install both with parameters

Create A records for both domains pointing to the same VM public IPv4. Allow **TCP 80**, **TCP 443**, and **UDP 8443** for this example:

```bash
sudo bash -c 'bash <(curl -fsSL --proto "=https" --tlsv1.2 \
  https://raw.githubusercontent.com/sxmad/mofatizi-installer/main/install.sh) all \
  --trojan-domain trojan.example.com \
  --hysteria2-domain hy2.example.com \
  --email you@example.com \
  --trojan-port 443 \
  --hysteria2-port 8443'
```

Alternatively, `--domain proxy.example.com` supplies one shared default hostname for both protocols. Each can have its own override. Both default ports are 443: Trojan uses **TCP**, Hysteria uses **UDP**, so they can share the number. Passwords, certificate caches and services remain independent.

The script does not create DNS records or modify GCP/host firewalls. GCP rules must match the VM's VPC and network tag/service account; checking “Allow HTTPS traffic” alone does not open UDP 443/8443 or TCP 8443.

## Add one protocol to an existing VM

With Trojan already on TCP 443, add Hysteria UDP 8443:

```bash
sudo bash -c 'bash <(curl -fsSL --proto "=https" --tlsv1.2 \
  https://raw.githubusercontent.com/sxmad/mofatizi-installer/main/install.sh) hysteria2 \
  --domain hy2.example.com \
  --email you@example.com \
  --port 8443'
```

With an older Hysteria installation already occupying TCP/UDP 443, add Trojan on TCP 8443:

```bash
sudo bash -c 'bash <(curl -fsSL --proto "=https" --tlsv1.2 \
  https://raw.githubusercontent.com/sxmad/mofatizi-installer/main/install.sh) trojan \
  --domain trojan.example.com \
  --email you@example.com \
  --port 8443'
```

New Hysteria installations use TCP 80 HTTP-01 and reserve no TCP HTTPS port by default. Their static page remains available over HTTP/3. Ordinary HTTPS is opt-in with `--hysteria2-https-port 9443`, requiring a free/allowed TCP port. Enabling that page on Trojan's TCP port is rejected.

**Legacy Hysteria:** older deployments may still require TCP 443 for TLS-ALPN and the HTTPS page. Existing configurations are not silently migrated. Use another Trojan TCP port, or explicitly reinstall Hysteria with its original domain, UDP port and password using the new installer to free TCP 443. Reinstalling that protocol can interrupt its current connections.

## Passwords and VM migration

Keep the original domain/SNI, protocol, port and password; update the domain A record to the new VM and obtain a valid certificate. A client configured with a hostname normally does not need editing. DNS caching and reconnects mean this is not a zero-interruption migration.

For one protocol, enter the original password without putting it in shell history or process arguments:

```bash
sudo bash -c '
set -e
IFS= read -r -s -p "Original Trojan password: " original_password
printf "\n"
[[ -n "$original_password" ]] || exit 1
printf "%s\n" "$original_password" |
  bash <(curl -fsSL --proto "=https" --tlsv1.2 \
    https://raw.githubusercontent.com/sxmad/mofatizi-installer/main/install.sh) trojan \
    --domain trojan.example.com \
    --email you@example.com \
    --port 443 \
    --password-stdin
'
```

For `all`, provide separate password files if retaining existing credentials:

```bash
sudo bash install.sh all \
  --domain proxy.example.com \
  --email you@example.com \
  --trojan-port 443 \
  --hysteria2-port 8443 \
  --trojan-password-file /root/trojan.password \
  --hysteria2-password-file /root/hysteria2.password
```

Create each file yourself with its password on the first line and restrict permissions, for example mode 600. Passwords accept 12–128 letters, digits, `.`, `_`, `-`. Empty/invalid explicit passwords fail; they are not replaced with random credentials. Do not commit password files to GitHub.

## Parameters

| Parameter | Meaning |
|---|---|
| `all`, `trojan`, `hysteria2` / `hy2` | Selection; omitted selection shows the menu. `--protocol NAME` is equivalent. |
| `--domain DOMAIN`, `--email EMAIL` | Default identity; missing values are prompted. |
| `--trojan-domain`, `--hysteria2-domain` | Protocol-specific hostname overrides. |
| `--acme-webroot DIR` | Existing HTTP website root, saved for issuance and renewal. |
| `--trojan-acme-webroot`, `--hysteria2-acme-webroot` | Override the shared webroot per protocol. |
| `--port PORT` | Port for a single selected protocol; rejected with `all`. |
| `--trojan-port`, `--hysteria2-port` | Separate TCP/UDP ports, both default 443. |
| `--hysteria2-https-port PORT` | Optional TCP HTTPS page; default 0/off, TCP 80 reserved. |
| `--password-stdin`, `--password-file PATH` | Original/custom password for a single protocol. |
| `--trojan-password-file`, `--hysteria2-password-file` | Separate password files, useful with `all`. |
| `--trojan-version`, `--hysteria2-version` | Core version selection, separate from pinned installer revisions. |
| `--no-bbr` | Skip Trojan kernel TCP BBR setup. |
| `--no-masquerade` | Omit the Hysteria page. |
| `--reinstall` | Explicitly replace selected existing configurations; child installers make backups. |
| `--yes` | Skip child overwrite confirmation; alone it does not enable replacement. |
| `--dry-run` | Show the plan without downloads or installation. |

`--reinstall` without a supplied password generates a **new** password. Use the password options to retain client configuration. Update/uninstall operations are provided by each protocol's own installer; this entry point does not add a second service manager.

## Execution and failures

The registry pins both child installers to reviewed commits and SHA256 digests. All selected downloads are checked before the first child runs. It fails closed on an invalid manifest, failed download, hash mismatch, or invalid Bash syntax. New protocols require a real adapter, parameter validation, a pinned revision/checksum, and tests; placeholder protocols are not shown in the menu.

Both certificate managers share the legacy-compatible `/run/lock/trojan-cert-renew.lock`, so new issuance/renewal does not race for TCP 80. Each protocol has its own timer and certificate files. Hysteria reads new certificates without restart; Trojan reloads certificates without a scheduled restart. Keep TCP 80 allowed for renewal. This does not automatically migrate old Hysteria TLS-ALPN certificate management.

If one child fails, the command returns nonzero and identifies any completed protocol. Existing and successfully installed services remain. A failed child can leave diagnostic configuration; fix the cause, then explicitly retry that protocol with `--reinstall` and the intended password. The script does not promise a cross-protocol rollback or declare an untested protocol usable.

Supported combined target: x86_64 Debian/Ubuntu with systemd. Individual installers retain their own requirements. After success, import the generated URI/QR into Shadowrocket and verify actual public connectivity.

## Validation

```bash
bash -n install.sh
python3 tests/test_installer.py
# Real binaries and pinned installer files; disposable host with free ports:
sudo env \
  TROJAN_BIN=/path/to/trojan \
  HYSTERIA_BIN=/path/to/hysteria \
  TROJAN_INSTALLER=/path/to/trojan-install.sh \
  HYSTERIA_INSTALLER=/path/to/hysteria-install.sh \
  python3 tests/test_coexist.py
```

CI tests the menu/arguments, preserving either existing protocol, password transport, rejected downloads, partial failure, and real TLS/SOCKS forwarding. Real coexistence checks cover both start orders on TCP/UDP 443, TCP 443 + UDP 8443, TCP 8443 + UDP 443, and custom ports. It also checks Hysteria certificate replacement without restarting either proxy and serialized certificate operations. These tests use a local CA/loopback target, not public ACME or your GCP firewall; Shadowrocket and multi-day stability still need real-deployment verification.

## Existing HTTP server on port 80

An older Trojan installation may include Nginx/Apache on TCP 80. HY2 on UDP 8443 can coexist with Trojan, but the default standalone HTTP-01 certificate solver cannot also bind TCP 80. **Do not stop the existing web server or change proxy ports to solve this.** Both child installers now support `--acme-webroot DIR` for issuance and future renewal through an existing HTTP server. They do not automatically edit that server's configuration.

1. Identify the listener with `sudo ss -ltnp 'sport = :80'`. If Nginx owns it, inspect its active HTTP server configuration (`sudo nginx -T`); verify which configuration directories it includes. Do not assume its document root.
2. Configure the exact new domain to serve the challenge files on public HTTP port 80. For a **new, separate hostname**, this example Nginx server block can go in a configuration file included by your existing Nginx. If that hostname already has a server block, adapt its challenge location instead of adding a duplicate. Preserve the old Trojan site's configuration.

```nginx
server {
    listen 80;
    server_name hy2.example.com;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/acme;
        default_type text/plain;
        try_files $uri =404;
    }

    location / { return 404; }
}
```

Create `/var/www/acme/.well-known/acme-challenge` with directory mode 755, then validate Nginx configuration with `sudo nginx -t` before `sudo systemctl reload nginx`. If the domain has an AAAA record, configure reachable IPv6 HTTP as well or remove an incorrect AAAA. A redirect at `server` level can override the challenge location; serve this path directly. Ensure the web server can traverse existing parent directories and read challenge files. No service stop/restart is needed.

3. Before requesting a certificate, place a temporary harmless text file in that challenge directory and confirm `http://hy2.example.com/.well-known/acme-challenge/YOUR_TEST_FILENAME` returns its exact contents (HTTP 200). Remove the test file afterward. Public TCP 80 must remain allowed for renewal.
4. Use the configured directory:

```bash
sudo bash -c 'bash <(curl -fsSL --proto "=https" --tlsv1.2 \
  https://raw.githubusercontent.com/sxmad/mofatizi-installer/main/install.sh) hysteria2 \
  --domain hy2.example.com \
  --email you@example.com \
  --port 8443 \
  --acme-webroot /var/www/acme'
```

The path is an example, not an autodetected default. The existing server must actually serve it for the requested domain. With `all`, `--acme-webroot DIR` applies to both pending protocols; per-protocol webroot flags override it. Both domain routes must work when sharing one directory. Without a webroot, the default remains a temporary standalone TCP 80 listener. Neither mode provides DNS-01.

### Retry after the official HY2 sample config was created

The official program installer can print “successfully installed” before certificate issuance and proxy verification. If an earlier run failed afterward, `/etc/hysteria/config.yaml` may be just its sample config. The unified installer preserves any existing config and will show `SKIP`; this does not mean HY2 works.

After fixing HTTP validation, run the command above with **`--reinstall`**, selecting **`hysteria2` only**. Confirm replacing/backing up the failed HY2 config, or add `--yes` for that explicitly selected protocol. Existing Trojan remains untouched. If HY2 previously worked, also provide its intended original password; otherwise a new password is generated. Do not use `all --reinstall` to recover only HY2.

The new preflight detects a persistent TCP 80 conflict before invoking the official HY2 installer. A later network/CA failure can still leave installation files, so explicit recovery remains necessary. Both renewers persist the selected webroot; keeping HTTP routing working avoids repeating this conflict at renewal time.

Reference: [lego HTTP-01 with an existing web server](https://go-acme.github.io/lego/obtain/http01/).
