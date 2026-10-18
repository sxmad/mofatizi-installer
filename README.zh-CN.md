# mofatizi-installer

[English](README.md) | [简体中文](README.zh-CN.md)

Trojan / Hysteria 2 统一入口，修订号 **2026-10-18.2**。支持菜单或参数安装；默认文档与页面元信息使用英文。

## 菜单

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

缺少域名/邮箱时会询问。`all` 依次安装缺少的协议，**已有配置默认跳过**，保留其密码、端口和运行状态。跳过不代表已对旧服务进行健康检查；不会停止其他协议抢端口。

## 一次安装两个

两个域名的 A 记录都指向同一 VM；此例放行 **TCP 80、TCP 443、UDP 8443**：

```bash
sudo bash -c 'bash <(curl -fsSL --proto "=https" --tlsv1.2 \
  https://raw.githubusercontent.com/sxmad/mofatizi-installer/main/install.sh) all \
  --trojan-domain trojan.example.com \
  --hysteria2-domain hy2.example.com \
  --email you@example.com \
  --trojan-port 443 \
  --hysteria2-port 8443'
```

也可用 `--domain proxy.example.com` 为两者指定同一个域名。默认均为 443，但 Trojan 使用 TCP、HY2 使用 UDP，可以共用号码。两者的密码、证书缓存和服务独立。

脚本不修改 DNS、GCP/主机防火墙。规则必须匹配 VM 的 VPC 和目标标记/服务账号；勾选 Allow HTTPS traffic 不代表已开放 UDP 或 TCP 8443。

## 已有一个，补装另一个

已有 Trojan TCP 443，添加 HY2 UDP 8443：

```bash
sudo bash -c 'bash <(curl -fsSL --proto "=https" --tlsv1.2 \
  https://raw.githubusercontent.com/sxmad/mofatizi-installer/main/install.sh) hysteria2 \
  --domain hy2.example.com \
  --email you@example.com \
  --port 8443'
```

已有旧版 HY2 TCP/UDP 443，添加 Trojan TCP 8443：

```bash
sudo bash -c 'bash <(curl -fsSL --proto "=https" --tlsv1.2 \
  https://raw.githubusercontent.com/sxmad/mofatizi-installer/main/install.sh) trojan \
  --domain trojan.example.com \
  --email you@example.com \
  --port 8443'
```

新版 HY2 使用 TCP 80 HTTP-01，默认仅提供 HTTP/3 页面，不额外占用 TCP 443。普通 HTTPS 页面可用 `--hysteria2-https-port 9443` 开启，需确保 TCP 端口空闲并放行。不能与 Trojan 的 TCP 端口冲突。

**旧 HY2** 可能仍在 TCP 443 上提供 TLS-ALPN 验证和 HTTPS 页面，脚本不会静默迁移旧配置。此时选其他 Trojan TCP 端口；如需释放 TCP 443，显式用新版重装 HY2，并传入原域名、UDP 端口和密码，接受短暂连接中断。

## 指定密码与迁移 VM

保持原域名/SNI、协议、端口和密码，将 A 记录指向新 VM 并申请有效证书。客户端使用域名时通常无需改配置；DNS 缓存和重连仍可能造成中断。

单协议可隐藏输入密码，不把密码写进命令参数：

```bash
sudo bash -c '
set -e
IFS= read -r -s -p "原 Trojan 密码: " original_password
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

`all` 可分别提供密码文件：

```bash
sudo bash install.sh all \
  --domain proxy.example.com \
  --email you@example.com \
  --trojan-port 443 \
  --hysteria2-port 8443 \
  --trojan-password-file /root/trojan.password \
  --hysteria2-password-file /root/hysteria2.password
```

自行创建密码文件，第一行为密码，并限制权限（例如 600）。支持 12–128 位字母、数字、点、下划线、短横线。显式密码为空/格式无效时中断，不会随机替换。不要把密码文件提交到 GitHub。

## 参数

| 参数 | 说明 |
|---|---|
| `all` / `trojan` / `hysteria2`（或 `hy2`） | 安装选择；`--protocol NAME` 等效；不填时显示菜单。 |
| `--domain` / `--email` | 通用域名和证书邮箱。 |
| `--trojan-domain` / `--hysteria2-domain` | 分别覆盖域名。 |
| `--port` | 单协议端口；`all` 不能使用此通用参数。 |
| `--trojan-port` / `--hysteria2-port` | TCP / UDP 端口，默认各 443。 |
| `--hysteria2-https-port` | 可选 TCP HTTPS 页面，默认 0（关闭），不能使用 TCP 80。 |
| `--password-stdin` / `--password-file` | 单协议原密码。 |
| `--trojan-password-file` / `--hysteria2-password-file` | 分别提供密码文件。 |
| `--trojan-version` / `--hysteria2-version` | 核心版本，与固定的子安装脚本版本独立。 |
| `--no-bbr` | 跳过 Trojan 内核 TCP BBR 设置。 |
| `--no-masquerade` | 不创建 HY2 页面。 |
| `--reinstall` | 显式覆盖所选已有配置；子安装器会备份。 |
| `--yes` | 跳过覆盖询问；单独使用不会启用覆盖。 |
| `--dry-run` | 只展示计划，不下载、不安装。 |

`--reinstall` 未传原密码时会生成新密码。更新/卸载使用各协议自己的安装器，本入口不另建服务管理系统。

## 执行、失败与扩展

子安装器固定到经过验证的提交及 SHA256；所有下载通过校验和 Bash 语法检查后才开始安装。清单无效、下载失败或哈希不符均中断。以后扩展协议时，需要注册实际安装器、参数适配、固定提交/哈希及测试；菜单不会显示未实现的占位协议。

证书签发和续期共用 `/run/lock/trojan-cert-renew.lock`，与旧 Trojan 续期任务兼容，避免同时占用 TCP 80。证书和 timer 分别管理；HY2 新握手读取新证书，Trojan 通过 reload 换证，不安排周期性重启。TCP 80 需保留放行。旧 HY2 的 TLS-ALPN 不会自动迁移。

如果第二个协议失败，返回非零状态并说明已完成的协议；保留原有和已成功服务。失败协议可能留下诊断配置，修复原因后需显式指定该协议 `--reinstall` 并传入预期密码。不进行跨协议卸载回滚，也不把失败协议宣称为可用。

组合安装目标为 x86_64 Debian/Ubuntu + systemd。安装完成后，在 Shadowrocket 导入对应链接/二维码并测试公网连接。

## 验证

```bash
bash -n install.sh
python3 tests/test_installer.py
sudo env \
  TROJAN_BIN=/path/to/trojan \
  HYSTERIA_BIN=/path/to/hysteria \
  TROJAN_INSTALLER=/path/to/trojan-install.sh \
  HYSTERIA_INSTALLER=/path/to/hysteria-install.sh \
  python3 tests/test_coexist.py
```

在一次性测试环境执行真实核心测试。CI 覆盖菜单、参数、保留任一已有协议、密码传递、下载校验和部分失败；真实测试覆盖两种启动顺序、TCP/UDP 443 同号、443/8443 组合、自定义端口、HY2 不重启换证，以及证书操作串行执行。使用本地 CA 和回环目标，不代替公网 ACME、GCP 防火墙、Shadowrocket 或多天运行测试。

## TCP 80 已有网站时

旧版 Trojan 安装方案可能包含长期占用 TCP 80 的 Nginx/Apache。HY2 的 UDP 8443 可以和 Trojan 共存，但默认的独立 HTTP-01 验证程序无法同时监听 TCP 80。改变代理端口不能解决此问题，也无需停止旧服务。

先执行 `sudo ss -ltnp 'sport = :80'` 确认进程。如果是 Nginx，再查看 `sudo nginx -T` 中实际加载的 HTTP 站点和目录。给 HY2 的**新域名**配置 HTTP 验证路径，让 `http://hy2.example.com/.well-known/acme-challenge/TOKEN` 读取 `/实际目录/.well-known/acme-challenge/TOKEN`。目录存在并不代表新域名会指向它；需要检查虚拟主机、重定向、访问权限及公网 TCP 80。不要假定网站一定在 `/var/www/html`。

可参考[英文页的 Nginx 配置示例](README.md#existing-http-server-on-port-80)，它为独立新域名增加验证站点，保留旧 Trojan 站点。已有该域名的站点时应修改其验证 location，不能重复添加同名 server。配置检查 `nginx -t` 通过后仅 reload，不停止旧服务；先用临时文本文件验证 HTTP 200 和内容正确，再申请证书。

两个单独安装器及统一入口均支持 `--acme-webroot DIR`。统一入口还支持 `--trojan-acme-webroot DIR` / `--hysteria2-acme-webroot DIR` 分别覆盖公共目录。签发与以后自动续期都会使用指定目录；安装后须保留该目录、网站路由和公网 TCP 80。

以下假设已正确配置 `/var/www/acme`，这是示例路径，不是自动探测结果：

```bash
sudo bash -c 'bash <(curl -fsSL --proto "=https" --tlsv1.2 \
  https://raw.githubusercontent.com/sxmad/mofatizi-installer/main/install.sh) hysteria2 \
  --domain hy2.example.com \
  --email you@example.com \
  --port 8443 \
  --acme-webroot /var/www/acme'
```

### 上一次安装失败后重试

官方 HY2 程序安装器显示成功，只代表核心和服务文件已放置，不代表证书和代理连接已可用。旧版本在证书失败前可能已经生成默认 `/etc/hysteria/config.yaml`。统一入口发现它会显示 `SKIP`，不等于 HY2 安装成功。

修复验证路径后，在上述命令增加 **`--reinstall`，仅选择 `hysteria2`**。确认备份覆盖失败的 HY2 配置；明确选择该协议后，也可增加 `--yes` 跳过覆盖确认。已有 Trojan 不受影响。如果 HY2 原来已有可用客户端，还应传入原密码，否则会生成新密码。不要用 `all --reinstall` 处理单个 HY2 失败。

新版本已将 TCP 80 占用检查提前到调用官方 HY2 安装器之前；后续网络或 CA 失败仍可能留下安装文件，因此不会自动覆盖所有已有配置。未指定 webroot 时仍使用独立 TCP 80 临时监听，当前不提供 DNS-01。
