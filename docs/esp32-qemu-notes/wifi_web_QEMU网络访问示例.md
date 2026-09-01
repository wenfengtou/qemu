# ESP32 联网访问网站示例（WiFi / QEMU 以太网双模式）

> 在 `blink` 跑通的基础上，新增 `wifi_web` 示例：连接网络后周期性 HTTP GET 一个网站，
> 打印状态码、响应头和正文片段。支持真机 WiFi 与 QEMU 模拟以太网两种模式，
> 上层 lwIP + HTTP 客户端代码完全共用。**已在 Windows 下实测 QEMU 访问公网成功。**

---

## 0. 结论速览（重要）

- **Windows 版 esp-qemu 现在可以访问外网。** 9.2.2（2026 构建）已把用户态网络栈
  slirp（libslirp）**静态链接**进 `qemu-system-xtensa.exe`，`-nic user,model=open_eth`
  开箱即用，guest 可经 NAT 访问宿主机和公网。
- 早期 Windows 预编译包没编入 slirp（QEMU 7.2 起 slirp 改为外部 `libslirp` 依赖），
  会报 `network backend 'user' is not compiled into this binary`，那时外网不通。
- **ping 不通是正常的**：slirp 只代理 TCP/UDP，不转发 ICMP。判断网络是否可用要用
  TCP（HTTP）而不是 ping。
- **DNS 要手动指定**：slirp 的 DHCP 不向 lwIP 下发 DNS，内置代理 `10.0.2.3` 在本环境
  解析失败；示例在拿到 IP 后手动设置 `223.5.5.5`（国内阿里，主）+ `8.8.8.8`（Google，备）。

---

## 1. QEMU slirp 网络原理

QEMU 用户态网络（slirp）在 QEMU 进程内跑一个网络栈做 NAT，guest 看到一组固定地址：

| guest 看到的地址 | 实际指向 |
|---|---|
| `10.0.2.15` | ESP32 虚拟机自己（DHCP 分配） |
| `10.0.2.2`  | 宿主机（你的电脑），转发到宿主机回环 `127.0.0.1` |
| `10.0.2.3`  | slirp 内置 DNS 代理（本环境不可用，改用公共 DNS） |
| 其他公网地址/域名 | 经 slirp NAT 从宿主机正常出公网 |

协议支持：**TCP / UDP 可用；ICMP（ping）不可用**。这是 slirp 的设计限制，非故障。

QEMU 启用网络的参数（`esp32` 机器内置 OpenCores 以太网 MAC）：

```
-nic user,model=open_eth
```

> 注意：此 esp-qemu 版本的 `esp32` 机器**没有 WiFi 无线模型**（二进制中无 wifi 相关符号），
> 只有 `open_eth` 以太网。真机 WiFi 代码照常编写，只是在 QEMU 里走以太网模拟。

---

## 2. 工程结构

```
wifi_web/
├── CMakeLists.txt              # 顶层，project(wifi_web)
├── partitions.csv              # 4MB flash 自定义分区（app 分区 2MB）
├── sdkconfig.defaults          # 默认配置（以太网模式 + open_eth + 4MB）
└── main/
    ├── CMakeLists.txt
    ├── Kconfig.projbuild       # menuconfig：网络接口选择 / SSID / 密码 / 目标网址
    ├── netif_demo.h            # 网络接口抽象头（事件组、init/start）
    ├── main.c                  # 主逻辑：等 IP → 周期 HTTP GET，打印结果
    ├── net_wifi.c              # WiFi STA 模式（真机，CONFIG_EXAMPLE_NETIF_WIFI）
    └── net_ethernet.c          # OpenCores 以太网模式（QEMU，CONFIG_EXAMPLE_NETIF_ETHERNET）
```

网络模式由 menuconfig 切换：`Example configuration → Network interface`

- `WiFi station`：真机硬件用
- `OpenCores Ethernet`：QEMU 仿真用（默认）

目标网址：`Example configuration → Example Web URL`（默认 `http://example.com/`，
改成 `https://` 开头会自动启用 TLS 与内置 CA 证书校验）。

---

## 3. 关键代码点

### 3.1 QEMU 以太网初始化（net_ethernet.c）

使用 OpenCores MAC + dp83848 PHY（QEMU 内部模拟，PHY 型号无实际影响）：

```c
eth_mac_config_t mac_config = ETH_MAC_DEFAULT_CONFIG();
eth_phy_config_t phy_config = ETH_PHY_DEFAULT_CONFIG();
phy_config.autonego_timeout_ms = 100;
phy_config.phy_addr = -1;
phy_config.reset_gpio_num = -1;
s_mac = esp_eth_mac_new_openeth(&mac_config);
s_phy = esp_eth_phy_new_dp83848(&phy_config);
esp_eth_config_t eth_config = ETH_DEFAULT_CONFIG(s_mac, s_phy);
esp_eth_driver_install(&eth_config, &s_eth_handle);
s_glue = esp_eth_new_netif_glue(s_eth_handle);
esp_netif_attach(eth_netif, s_glue);
// 注册 IP_EVENT_ETH_GOT_IP 事件 → esp_eth_start()
```

需要在 sdkconfig 打开 `CONFIG_ETH_USE_OPENETH=y`（已在 sdkconfig.defaults 中）。

### 3.2 手动设置 DNS（解决 getaddrinfo 失败）

拿到 IP 后（`IP_EVENT_ETH_GOT_IP`）设置公共 DNS：

```c
#include "lwip/dns.h"
ip_addr_t dns0, dns1;
IP_ADDR4(&dns0, 223, 5, 5, 5);   // 阿里 DNS（国内）
IP_ADDR4(&dns1, 8, 8, 8, 8);     // Google DNS（海外）
dns_setserver(0, &dns0);
dns_setserver(1, &dns1);
```

> 若不设置，HTTP 请求会报：
> `esp-tls: couldn't get hostname for :example.com: getaddrinfo() returns 202`

### 3.3 HTTP 客户端（main.c）

`esp_http_client_perform()` 阻塞完成一次 GET，事件处理器里累积正文片段，
perform 返回后打印状态码、Content-Length 和前 256 字节正文。每 10 秒重复一次。

---

## 4. 构建与运行

### 4.1 一键脚本（推荐）

```bat
:: 编译 + 合并 4MB flash 镜像
D:\work\Esp32Qume\build_wifi_web.bat

:: 联网运行 QEMU（以太网模式）
D:\work\Esp32Qume\run_web_qemu.bat
```

### 4.2 手动命令

编译（沿用 blink 的 wrapper + 手动环境变量套路，见《开发环境搭建全记录》）：

```bash
export IDF_PATH="D:/Espressif/frameworks/esp-idf-v5.5.5"
export IDF_TOOLS_PATH="D:/Espressif"
export IDF_PYTHON_ENV_PATH="D:/Espressif/python_env/idf5.5_py3.11_env"
export ESP_ROM_ELF_DIR="D:/Espressif/tools/esp-rom-elfs/20241011/"
export PATH="/d/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20260121/xtensa-esp-elf/bin:/d/Espressif/tools/cmake/3.30.2/bin:/d/Espressif/tools/ninja/1.12.1:/d/Espressif/tools/idf-git/2.44.0/cmd:/d/Espressif/python_env/idf5.5_py3.11_env/Scripts:$PATH"

PY="D:/Espressif/python_env/idf5.5_py3.11_env/Scripts/python.exe"
WRAP="D:/work/Esp32Qume/.idf_wrapper.py"

cd "D:/work/Esp32Qume/wifi_web"
"$PY" "$WRAP" build

# 合并 + 填充到 4MB（用官方 @flash_args，--fill-flash-size 自动补 0xFF）
cd build
"D:/Espressif/python_env/idf5.5_py3.11_env/Scripts/esptool.exe" --chip esp32 \
  merge_bin --fill-flash-size 4MB -o flash_image.bin @flash_args
```

运行 QEMU（关键是 `-nic user,model=open_eth`）：

```bash
cd "D:/work/Esp32Qume/qemu/bin"
./qemu-system-xtensa.exe -M esp32 -nographic \
  -drive file="D:/work/Esp32Qume/wifi_web/build/flash_image.bin",if=mtd,format=raw \
  -nic user,model=open_eth
```

退出：`Ctrl+A` 然后按 `X`，或直接关窗口。

---

## 5. 实测结果（2026-08-30）

### 5.1 公网访问 example.com（真实出网）

```
I (xxxx) eth: 以太网链路已连接
I (xxxx) esp_netif_handlers: eth ip: 10.0.2.15, mask: 255.255.255.0, gw: 10.0.2.2
I (xxxx) eth: 以太网获取到 IP: 10.0.2.15
I (xxxx) eth: 已设置 DNS: 223.5.5.5 (主), 8.8.8.8 (备)
I (xxxx) web: 网络已就绪！
...
I (38753) web: 响应头: Server = cloudflare
I (38763) web: 响应头: CF-RAY = a3330e3918764fc8-HKG
I (38763) web: 响应结束，正文总长度 559 字节
I (38763) web: ==== GET http://example.com/ ====
I (38763) web: HTTP 状态码: 200, Content-Length: -1
```

DNS 经 `223.5.5.5` 解析成功，TCP 连到 Cloudflare 边缘（香港 HKG 节点），返回 200，
每 10 秒重复成功。**证明 Windows 下 guest 可正常访问公网。**

### 5.2 访问宿主机（10.0.2.2）

在电脑上 `python -m http.server 80`，固件网址设为 `http://10.0.2.2/test.html`：

```
I (16388) web: HTTP 状态码: 200, Content-Length: 108
I (16388) web: 正文片段(前108字节):
<html><body><h1>Hello from host via QEMU slirp gateway 10.0.2.2</h1>...
```

即使服务只监听 `127.0.0.1`，guest 也能通过 `10.0.2.2` 访问（slirp 从宿主机内部连回环）。

---

## 6. 真机用 WiFi

1. menuconfig → `Example configuration → Network interface` 选 `WiFi station`
2. 设置 `WiFi SSID` 和 `WiFi Password`
3. 正常 `idf.py build flash monitor`（真机不需要 `-nic` 参数，也无需手动 DNS）

真机上 `net_wifi.c` 走 `esp_wifi` STA 模式，`IP_EVENT_STA_GOT_IP` 后同样进入 HTTP 循环。

---

## 7. FAQ

**Q：ping 10.0.2.2 或 ping 公网都不通？**
A：正常。slirp 不转发 ICMP，用 HTTP/TCP 验证。

**Q：报 `getaddrinfo() returns 202` / `ESP_ERR_HTTP_CONNECT`？**
A：DNS 没设对。确认拿到 IP 后调用了 `dns_setserver()` 设置公共 DNS（见 3.2）。

**Q：报 `network backend 'user' is not compiled into this binary`？**
A：该 QEMU 二进制没编入 slirp。换用本项目 `qemu/` 下 9.2.2 版本（已静态链接 libslirp）。

**Q：能访问 HTTPS 网站吗？**
A：可以。网址改成 `https://` 开头，示例已配置 `crt_bundle_attach`（内置 CA 证书校验），
TLS 走 TCP 443，slirp 同样支持。

**Q：WiFi 模式能在 QEMU 跑吗？**
A：不能。此版本 esp32 机器无无线模型，WiFi 模式仅用于真机；QEMU 用以太网模式。
