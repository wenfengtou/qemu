# Arduino-ESP32 在 fork QEMU 上的适配全记录

> 目标：用用户 fork 的 QEMU（`qianmayi/qemu` 的 `picsimlab-esp32` 分支）编译出 `qemu-system-xtensa.exe`，
> 再编写一个 Arduino 程序（WiFi 联网 + 访问网站），在 QEMU 的 `esp32-picsimlab` 机型 + `esp32_wifi` 网卡上跑通。
> 完成日期：2026-09-01

---

## 0. 结论速览

- **Arduino 程序可以在 fork QEMU 上稳定联网访问公网。** 最终串口输出：
  ```
  WiFi connected!
    IP: 10.0.2.15  Gateway: 10.0.2.2  DNS: 223.5.5.5
  HTTP status code: 200   Body length: 559 bytes
  ```
- 关键突破：修复了 `esp32_wifi_ap.c` 下行数据帧的 **802.11 方向位（FromDS）**，使
  Arduino-ESP32 3.x 的 lwIP 栈能接受 DHCP offer/ACK 广播帧，从而拿到 IP。
- 三个配套坑：WiFi 连接失败（去掉 AP 扫描）、slirp 内置 DNS 不回包（手动设公共 DNS）、
  `WiFi.config(INADDR_NONE,...)` 会清掉 DHCP IP（删除该调用）。
- 一键运行：双击 [run_arduino.bat](computer://d:\work\Esp32Qume\run_arduino.bat)。

---

## 1. 环境概览

| 项目 | 版本 / 位置 |
|------|-------------|
| 操作系统 | Windows 10 |
| fork QEMU 源码 | `D:\work\Esp32Qume\myself\qemu`（分支 `picsimlab-esp32`） |
| QEMU 产物 | `myself\qemu\build\qemu-system-xtensa.exe`（约 67 MB，版本 `9.2.2 (qianmayi-fork-windows)`） |
| 编译环境 | MSYS2 MINGW64（`D:\msys64`，gcc 14.x） |
| Arduino-ESP32 core | `3.3.10-cn`（位于 `C:\Users\lwf\AppData\Local\Arduino15\packages\esp32\hardware\esp32\3.3.10-cn`） |
| arduino-cli | `D:\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe` |
| 例程目录 | `D:\work\Esp32Qume\arduino_wifi_web` |
| ROM 目录 | `D:\work\Esp32Qume\qemu-standalone\qemu-bundle\qemu\share` |

---

## 2. fork QEMU 编译（Windows 构建修复）

### 2.1 两处源码修改

直接 `configure && ninja` 在 Windows 上会遇到两个问题，均已修复并提交：

1. **`meson.build`：slirp 静态链接导致 glib 符号多重定义**
   MinGW 下静态 libslirp 与 QEMU 的 glib 符号冲突，链接期报大量
   `multiple definition of 'g_*'`。改为动态链接：
   ```meson
   slirp_dep = dependency('slirp', required: get_option('slirp'),
                          method: 'pkg-config',
                          static: false)
   ```

2. **`scripts/symlink-install-tree.py`：Windows 无管理员/开发者模式无法建符号链接**
   回退为文件复制：
   ```python
   if os.name == 'nt':
       if not os.path.lexists(bundle_dest):
           if os.path.isfile(source):
               try:
                   import shutil
                   shutil.copyfile(source, bundle_dest)
               except BaseException as copy_err:
                   print(f'warning: could not copy {dest}: {copy_err}',
                         file=sys.stderr)
       continue
   ```

### 2.2 版本生成坑（无 tag 仓库）

重编时 `qemu-version.h` 会执行 `git describe`，而 fork 仓库**没有任何 tag**，报
`fatal: No names found, cannot describe anything`，导致构建中断。解决：给 meson 传
`pkgversion`，让 `scripts/qemu-version.sh` 跳过 git：

```bash
meson configure -Dpkgversion=qianmayi-fork-windows
```

产物版本号变为 `9.2.2 (qianmayi-fork-windows)`。

### 2.3 编译命令

在 **MSYS2 MINGW64 终端**中（不是 PowerShell，PowerShell 下 QAPI 生成步骤会因缺
`/usr/bin` 工具而报 `WinError 2`）：

```bash
cd /d/work/Esp32Qume/myself/qemu
mkdir -p build && cd build
../configure --target-list=xtensa-softmmu \
             --enable-slirp --enable-gcrypt \
             --disable-werror --disable-docs
ninja -j8
```

> 提示：`qemu-system-xtensa.exe` 动态链接 `libslirp-0.dll` 等 MinGW64 DLL，运行时需把
> `D:\msys64\mingw64\bin` 加入 PATH（`run_arduino.bat` 已处理）。

---

## 3. Arduino-ESP32 core 安装

- 版本：`3.3.10-cn`（国内定制版，GitHub 直连太慢，用极狐镜像下载安装）。
- 安装位置：`C:\Users\lwf\AppData\Local\Arduino15\packages\esp32\`
  - `hardware\esp32\3.3.10-cn\`（core 本体）
  - `tools\`（xtensa-esp-elf-gdb、esptool_py 等工具链）

---

## 4. Arduino 例程 `arduino_wifi_web`

### 4.1 源码要点

源码：[arduino_wifi_web.ino](computer://d:\work\Esp32Qume\arduino_wifi_web\arduino_wifi_web.ino)

- 连接 QEMU 模拟的开放热点 `PICSimLabWifi`（无密码）。
- **不要调用 `WiFi.scanNetworks()`**：QEMU 环境里有多个模拟 AP，扫描会干扰 station
  状态机/DHCP 注入，导致连接失败（status=6）。
- 拿到 IP 后手动把 DNS 设为公共 DNS `223.5.5.5`（绕过 slirp 内置 DNS 不回包的问题），
  用 `esp_netif_set_dns_info()` 直接改 netif，**不要用 `WiFi.config(INADDR_NONE,...)`**
  （那会用空地址重配接口、清掉 DHCP 拿到的 IP）。
- 每次 HTTP 请求前调用 `forceQemuDns()` 重设 DNS（lwIP 可能把 DNS 重置回 10.0.2.3）。

### 4.2 编译命令（关键参数）

必须用 **DIO** 模式：QEMU 模拟的 flash 不支持 QIO，用 QIO 启动即崩溃。

```bat
"D:\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe" compile ^
  --fqbn esp32:esp32:esp32:FlashMode=dio,FlashFreq=40,FlashSize=4M,PartitionScheme=default,PSRAM=disabled ^
  --build-path D:\work\Esp32Qume\arduino_wifi_web\build ^
  D:\work\Esp32Qume\arduino_wifi_web
```

编译成功标志：
```
Sketch uses 1031744 bytes (78%) of program storage space. Maximum is 1310720 bytes.
```

### 4.3 合并 4MB flash 镜像

arduino-cli 会自动生成 `build\arduino_wifi_web.ino.merged.bin`（4MB，含
bootloader + 分区表 + app），QEMU 直接加载它即可。

---

## 5. 关键问题与修复（按时间顺序）

### 5.1 WiFi 连接失败 status=6

- 现象：`WiFi.begin()` 后一直连不上，状态码 6（`WL_DISCONNECTED`）。
- 原因：例程先 `WiFi.scanNetworks()` 扫描，QEMU 环境多个模拟 AP 干扰了 station 状态机。
- 修复：去掉扫描，直接 `WiFi.begin(WIFI_SSID)` 并带重试。

### 5.2 DHCP 超时（核心修复：FromDS 方向位）

- 现象：关联成功（status=3）但一直拿不到 IP，DHCP 超时。
- 根因：`hw/misc/esp32_wifi_ap.c` 的 `Esp32_WLAN_receive()` 把从 slirp 发给 station 的
  下行数据帧方向位设成了 **ToDS(0x1)**。对 AP→station 的帧，802.11 方向位必须是
  **FromDS(0x2)**。Arduino-ESP32 3.x 的新 lwIP 栈会丢弃方向位错误的帧，于是 DHCP
  offer/ACK 广播帧从未被接受。
- 修复：把 `frame->frame_control.flags=1` 改为 `0x2`（与 `create_data_packet()` 一致）：
  ```c
  if(s->ap_state==Esp32_WLAN__STATE_STA_ASSOCIATED) {
      /* Downlink frame from the AP (slirp) to the station: the
       * FromDS bit (0x2) must be set, NOT ToDS (0x1). ... */
      frame->frame_control.flags=0x2;
      ...
  }
  ```
- 提交：`0db01f6 wifi-ap: set FromDS (0x2) on downlink frames to the station`
- 只改了 station 模式路径；softAP 分支保持上游原值（未实测不擅动）。

### 5.3 DNS 解析失败

- 现象：拿到 IP 后 `getaddrinfo` 失败 / HTTP 连不上。
- 根因：Windows 下 slirp 内置 DNS 代理 `10.0.2.3` 不回包；DHCP 下发的 DNS 不可用。
- 修复：用 `esp_netif_set_dns_info()` 把 DNS 设为公共 DNS `223.5.5.5`（主）+ `8.8.8.8`（备），
  查询经 slirp NAT 转发出公网。

### 5.4 WiFi.config(INADDR_NONE) 清掉 IP 的坑

- 现象：联网正常（HTTP 200），但 `WiFi connected!` 后的摘要打印 `IP: 0.0.0.0`。
- 根因：想"只改 DNS"而调用 `WiFi.config(INADDR_NONE, INADDR_NONE, INADDR_NONE, dns)`，
  它用空地址重配 STA 接口，把 DHCP 拿到的 IP 清掉了（底层 netif 租约仍在，HTTP 照常）。
- 修复：删除该调用，DNS 统一走 `esp_netif_set_dns_info()`。

---

## 6. 运行

### 6.1 一键运行

双击 [run_arduino.bat](computer://d:\work\Esp32Qume\run_arduino.bat)（已把
`D:\msys64\mingw64\bin` 加入 PATH 以加载 libslirp DLL）。

### 6.2 等价命令

```bat
qemu-system-xtensa.exe -L D:\work\Esp32Qume\qemu-standalone\qemu-bundle\qemu\share ^
  -M esp32-picsimlab -nographic ^
  -drive file=D:\work\Esp32Qume\arduino_wifi_web\build\arduino_wifi_web.ino.merged.bin,if=mtd,format=raw ^
  -nic user,model=esp32_wifi ^
  -global driver=timer.esp32.timg,property=wdt_disable,value=true
```

参数说明：

| 参数 | 含义 |
|------|------|
| `-L <share>` | ROM 搜索目录（`esp32-v3-rom.bin` 等，缺失报 `ROM code binary not found`） |
| `-M esp32-picsimlab` | fork 分支新增机型，含 `esp32_wifi` 网卡 |
| `-drive file=...,if=mtd` | 加载 4MB 合并 flash 镜像 |
| `-nic user,model=esp32_wifi` | slirp 用户态网络 + WiFi 模型 |
| `wdt_disable` | 关闭看门狗，方便长时间观察 |

退出：`Ctrl+A` 再按 `X`。

---

## 7. 实测结果（2026-09-01）

```
ESP32 QEMU WiFi + Web (Arduino)  demo
Connecting to open AP 'PICSimLabWifi' (no scan, with retries)...
connect attempt 1 ...
status=3
waiting for DHCP IP [10.0.2.15]
DNS overridden to 223.5.5.5 via esp_netif
  IP=10.0.2.15  GW=10.0.2.2  DNS=223.5.5.5
WiFi connected!
  IP:      10.0.2.15
  Gateway: 10.0.2.2
  DNS:     223.5.5.5

---- GET http://example.com/ ----
HTTP status code: 200
Body length: 559 bytes
<!doctype html><html lang="en"><head><title>Example Domain</title>...
```

连续多次 GET 均返回 200，稳定复现。

---

## 8. Git 提交记录（fork 仓库 `myself/qemu`，分支 `picsimlab-esp32`）

```
65d68c0 build: fix MSYS2/mingw Windows build
        （meson slirp 动态链接、symlink 回退复制）
0db01f6 wifi-ap: set FromDS (0x2) on downlink frames to the station
        （核心 WiFi 修复，解决 Arduino-ESP32 3.x DHCP 超时）
2b11e3a revert sim.c is_default change to keep upstream code untouched
        （按用户要求恢复 sim.c 为上游原样，不修改原始代码）
```

> 提交目前仅在本地，未推送远端。

---

## 9. FAQ

**Q：Arduino 程序在 QEMU 里能跑 WiFi 吗？**
A：能。本 fork 的 `esp32-picsimlab` 机型带 `esp32_wifi` 网卡，配合 FromDS 修复，
Arduino-ESP32 3.x 可正常关联、DHCP、联网。注意：官方 esp-qemu（Espressif 版）的
`esp32` 机型没有 WiFi 模型，只有 `open_eth` 以太网，跑不了 Arduino WiFi 代码。

**Q：为什么必须用 DIO 而不是 QIO？**
A：QEMU 模拟的 flash 只支持 DIO，QIO 启动即崩溃。

**Q：为什么 ping 不通？**
A：slirp 用户态网络只转发 TCP/UDP，不转发 ICMP。用 HTTP 验证网络。

**Q：DNS 为什么要手动设？**
A：Windows 下 slirp 内置 DNS `10.0.2.3` 不回包。拿到 IP 后把 DNS 设为公共 DNS
（`223.5.5.5` / `8.8.8.8`），查询经 slirp NAT 转发。真机不需要这段。

**Q：能访问 HTTPS 吗？**
A：可以。URL 改成 `https://` 开头即可，TLS 走 TCP 443，slirp 同样支持。
