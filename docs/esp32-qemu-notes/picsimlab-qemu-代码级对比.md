# picsimlab-qemu 与官方 esp-qemu 代码级对比

> 对比对象：
> - 官方：[espressif/qemu](https://github.com/espressif/qemu) 的 `esp-develop` 分支（你 `qemu/` 目录里 9.2.2 预编译版的来源）
> - 教学增强版：[lcgamboa/qemu](https://github.com/lcgamboa/qemu) 的 `picsimlab-esp32` 分支（为 [PICsimLab](https://github.com/lcgamboa/picsimlab) 图形化仿真器定制）
>
> 两者 `VERSION` 均为 **9.2.2**。picsimlab 分支是在官方 `esp-develop`（已 rebase 到 QEMU 9.2）之上打的一层补丁，CPU、中断、flash、定时器、以太网等绝大多数模拟代码直接沿用官方。

---

## 1. 项目定位

| | 官方 espressif/qemu | lcgamboa picsimlab-esp32 |
|---|---|---|
| 维护方 | 乐鑫官方 | PICsimLab 作者 lcgamboa（个人） |
| 目的 | 通用 ESP32 固件仿真、CI 测试 | 给 PICsimLab 教学 GUI 当后端，需要面板实时交互 |
| 基线 | QEMU 9.2.x esp-develop | **同一 esp-develop 9.2.2 再叠加补丁** |
| 产物 | 独立 `qemu-system-xtensa.exe` | 额外编译为动态库 `libqemu-xtensa.so` 供 GUI 链接 |
| WiFi | 不模拟（以太网 open_eth） | **模拟真实 WiFi MAC**（STA + SoftAP） |

---

## 2. 新增/改动文件清单（代码量）

picsimlab 分支相对官方新增约 **3800+ 行** ESP 相关代码：

| 文件 | 行数 | 作用 | 官方是否有 |
|------|------|------|-----------|
| `hw/xtensa/esp32_picsimlab.c` | 1056 | ESP32 picsimlab 机型（在官方 `esp32.c` 857 行基础上扩展） | 无 |
| `hw/riscv/esp32c3_picsimlab.c` | 1091 | ESP32-C3 picsimlab 机型 | 无 |
| `hw/misc/esp32_wifi.c` | 171 | ESP32 WiFi MAC 寄存器/DMA 模拟 | 无 |
| `hw/misc/esp32c3_wifi.c` | 172 | C3 版 WiFi MAC | 无 |
| `hw/misc/esp32_wifi_ap.c` | 719 | 虚拟 AP / 802.11 帧处理（关联、认证、收发） | 无 |
| `hw/misc/esp32_wlan_packet.c` | 279 | 802.11 帧封包/解析工具 | 无 |
| `hw/i2c/picsimlab_i2c.c` | 96 | 面板 I2C 外设钩子 | 无 |
| `hw/ssi/picsimlab_spi.c` | 58 | 面板 SPI 外设钩子 | 无 |
| `build_libqemu-esp32.sh` | 60 | 把 QEMU 编译成动态库的脚本 | 无 |

构建清单（meson.build）的改动印证了新增文件：
- `hw/misc/meson.build`：ESP32 段比官方多出 `esp32_wifi.c`、`esp32_wifi_ap.c`、`esp32_wlan_packet.c`、`esp32_ana.c`、`esp32_fe.c`、`esp32_phya.c`、`esp32_iomux.c`；C3 段多出 `esp32c3_wifi.c` 等。
- `hw/xtensa/meson.build`：`files('esp32.c','esp32_intc.c','esp32_picsimlab.c')`（官方只有前两个）。
- `hw/riscv/meson.build`：加入 `esp32c3_picsimlab.c`。
- `hw/i2c/meson.build`：`CONFIG_PICSIMLAB_I2C` 时编译 `picsimlab_i2c.c`。
- `hw/ssi/meson.build`：加入 `picsimlab_spi.c`。

> 官方 `hw/misc/meson.build` 的 ESP32 段只有 9 个基础外设：`esp32_crosscore_int / dport / rng / rtc_cntl / sha / aes / ledc / flash_enc / ssi_psram`，**没有任何 wifi 文件**。

---

## 3. 最核心差异：WiFi 从「未实现」到「真模拟」

### 3.1 官方：WiFi 寄存器区标记为未实现

官方 `hw/xtensa/esp32.c` 把 WiFi 相关地址空间直接挂成 unimplemented device，固件一旦访问 WiFi MAC 寄存器就落空；网络只有 OpenCores 以太网：

```c
// 官方 hw/xtensa/esp32.c
esp32_soc_add_unimp_device(sys_mem, "esp32.chipv7_phyb", DR_REG_WDEV_BASE, 0x1000, 0);
esp32_soc_add_unimp_device(sys_mem, "esp32.unknown_wifi", DR_REG_NRX_BASE - 0x0C00, 0x1000, -1);
esp32_soc_add_unimp_device(sys_mem, "esp32.unknown_wifi1", DR_REG_BB_BASE, 0x1000, -1);
// 网络只有 open_eth（DR_REG_EMAC_BASE）
```

### 3.2 picsimlab：在同一地址实例化真实 WiFi MAC

`hw/xtensa/esp32_picsimlab.c` 检测到 `-nic model=esp32_wifi` 时，创建 WiFi 设备、挂到 WiFi 寄存器基址并连接 WiFi MAC 中断：

```c
// picsimlab hw/xtensa/esp32_picsimlab.c
nd = qemu_find_nic_info(TYPE_ESP32_WIFI, false, NULL);
if (nd != NULL) {
    qdev_set_nic_properties(DEVICE(&ss->wifi), nd);
    sbd = SYS_BUS_DEVICE(DEVICE(&ss->wifi));
    sysbus_realize_and_unref(sbd, &error_fatal);
    esp32_soc_add_periph_device(sys_mem, &ss->wifi, DR_REG_WIFI_BASE);
    sysbus_connect_irq(..., qdev_get_gpio_in(DEVICE(&ss->intmatrix),
                       ETS_WIFI_MAC_INTR_SOURCE));
}
```

### 3.3 WiFi MAC 的工作原理（寄存器 + DMA 层）

`hw/misc/esp32_wifi.c` 模拟的是 ESP32 WiFi MAC 的寄存器和 DMA 描述符，而不是简单的网络转发：

- **发送（guest→AP）**：固件写 `A_WIFI_DMA_OUTLINK` 启动 DMA 时，模拟器从 guest 内存读出 802.11 帧（`mac80211_frame`），交给 `Esp32_WLAN_handle_frame()` 处理。
- **接收（AP→guest）**：`Esp32_sendFrame()` 构造一个带 `wifi_pkt_rx_ctrl_t` 接收头（含伪造的 RSSI、信道 rate、noise_floor、时间戳）的帧，写回 guest 的 DMA 接收缓冲，更新 DMA 描述符，再触发中断 `0x1000024`。
- **地址过滤**：`match_mac_address()` 按帧目的 MAC / BSSID 是否匹配设备里存的 MAC（`mem+0x40`、`mem+0x48`）来设置 `damatch0/1`、`bssidmatch0/1`，与真实硬件行为一致。

这样上层 `esp_wifi` 驱动完全以为在操作真实无线网卡，实际 802.11 帧通过 QEMU 的 slirp user 网络（或 socket 多播）收发。WiFi 代码移植自更老的社区 fork [a159x36/qemu](https://github.com/a159x36/qemu)。

### 3.4 虚拟 AP 的限制

`hw/misc/esp32_wifi_ap.c` 内置 3 个**硬编码开放热点**（无密码），Station 模式只能连这三个 SSID：

```c
// hw/misc/esp32_wifi_ap.c
{"PICSimLabWifi", 1, -25, {0x10,0x01,0x00,0xc4,0x0a,0x56}},
{"Espressif",      5, -30, {0x10,0x01,0x00,0xc4,0x0a,0x51}},
{"MasseyWifi",    10, -40, {0x10,0x01,0x00,0xc4,0x0a,0x52}}
```

字段含义：SSID、信道号、信号强度(dBm)、BSSID。固件里连 WiFi 时 SSID 填这三个之一、密码留空即可。

### 3.5 ESP-NOW 多机组网

WiFi 设备也支持 `-nic socket` 后端，用多播地址把多个 QEMU 实例组网，用于 ESP-NOW 协议：

```
-nic socket,model=esp32_wifi,id=u1,mcast=230.0.0.1:1234
```

每台设备需在 efuse 文件里配置不同 MAC（ESP32 MAC 在 efuse 偏移 0x4–0x9、CRC 在 0xA；C3 在 0x18–0x1D）。

---

## 4. 第二差异：GUI 面板回调钩子

picsimlab 机型导出一组函数指针回调，让外部 GUI 实时读写引脚/外设，官方完全没有：

```c
// hw/xtensa/esp32_picsimlab.c
typedef struct {
    void (*picsimlab_write_pin)(int pin, int value);                 // GPIO 电平 → 面板 LED
    void (*picsimlab_dir_pin)(int pin, int value);                   // GPIO 方向
    int  (*picsimlab_i2c_event)(uint8_t id, uint8_t addr, uint16_t ev);  // I2C 事件
    uint8_t (*picsimlab_spi_event)(uint8_t id, uint16_t ev);         // SPI 事件
    void (*picsimlab_uart_tx_event)(uint8_t id, uint8_t value);      // 串口字节 → 虚拟 COM
    void (*picsimlab_rmt_event)(uint8_t ch, uint32_t cfg, uint32_t v);   // RMT（红外/WS2812）
    const short int *pinmap;
} callbacks_t;

void qemu_picsimlab_register_callbacks(void *arg);  // GUI 启动时注入实现
void qemu_picsimlab_set_pin(int pin, int value);    // 面板按键 → 注入电平
void qemu_picsimlab_set_apin(int chn, int value);   // 模拟量
void qemu_picsimlab_uart_receive(int id, const uint8_t *buf, int size);  // 虚拟 COM → guest
```

这些回调默认指向空函数 `place_holder()`，因此**不接 GUI、当普通 QEMU 命令行跑也能正常工作**；被 PICsimLab 加载后，GUI 就能在图形面板上点按键、看 LED、接虚拟示波器/显示器。GPIO 变化通过 `qdev_connect_gpio_out_named(... ESP32_GPIOS/DIR ...)` 转发到 `picsimlab_write_pin/dir_pin`。

---

## 5. 第三差异：动态库化构建

官方产出独立可执行文件。picsimlab 的 `build_libqemu-esp32.sh` 在正常 `make` 之后，通过 ninja 响应文件（`.rsp`）把链接命令里的 `system_main.c.o`（含 `main()`）剔除、加 `-shared`，改产出动态库：

```sh
# 正常编译后，在 build/ 里：
sed -i 's/.*system_main.c.o//g' qemu-system-xtensa.rsp
sed -i 's/-o qemu-system-xtensa/-shared -o libqemu-xtensa.so/g' qemu-system-xtensa.rsp
eval "$CMD -ggdb @qemu-system-xtensa.rsp"
```

同时构建 xtensa 和 riscv32 两个目标的动态库。注意该脚本只处理 Linux/macOS（`nproc`/`sysctl`），**Windows 下编译动态库需自行改造**；但机型/WiFi 代码是平台无关 C，理论上可编成独立 `qemu-system-xtensa.exe`。

---

## 6. 命令行用法对比

| 用途 | 官方 esp-qemu | picsimlab 分支 |
|------|--------------|----------------|
| 机型 | `-M esp32` | `-M esp32-picsimlab`（也保留 `-M esp32`） |
| 以太网 | `-nic user,model=open_eth` | 同左（open_eth 仍可用） |
| **WiFi STA** | 不支持 | `-nic user,model=esp32_wifi,net=192.168.4.0/24,hostfwd=tcp::16555-192.168.4.15:80` |
| WiFi（C3） | 不支持 | `-nic user,model=esp32c3_wifi` |
| ESP-NOW | 不支持 | `-nic socket,model=esp32_wifi,id=u1,mcast=230.0.0.1:1234` |
| GDB | `-s -S` 或 `-gdb tcp::1234` | 同左（PICsimLab 常用 `-gdb tcp::1234` + 关看门狗） |
| efuse | 可选 | 用 WiFi/ESP-NOW 时需提供 efuse 文件设 MAC |

WiFi 完整启动示例（来自分支 README）：

```
qemu-system-xtensa -M esp32-picsimlab \
  -drive file=flash_image.bin,if=mtd,format=raw \
  -drive file=esp32.efuse,if=none,format=raw,id=efuse \
  -global driver=nvram.esp32.efuse,property=drive,value=efuse \
  -serial stdio -gdb tcp::1234 \
  -global driver=timer.esp32.timg,property=wdt_disable,value=true \
  -nic user,model=esp32_wifi,net=192.168.4.0/24,hostfwd=tcp::16555-192.168.4.15:80
```

---

## 7. 对本项目的实际意义

- **好处**：固件可以**原样用 `esp_wifi` STA 连 WiFi**（不必像当前 `wifi_web` 那样改用以太网 open_eth），在 QEMU 里跑与真机一致的 WiFi 代码路径；配合 PICsimLab 还能图形化交互。
- **代价/限制**：
  - AP 是硬编码开放热点（SSID 固定、无密码、无 WPA）。
  - 主要为 PICsimLab GUI 设计，官方不提供 Windows 动态库/独立 exe 的现成构建脚本。
  - 属于个人维护分支，跟进官方 esp-develop 的节奏可能滞后。
- **建议**：纯命令行跑网络，官方 9.2.2 + open_eth（已验证可出公网）更省心；要测 `esp_wifi`/ESP-NOW 代码路径或做教学演示，再用 picsimlab 分支。

---

## 附：源码位置

- 官方：https://github.com/espressif/qemu （分支 `esp-develop`）
- picsimlab：https://github.com/lcgamboa/qemu （分支 `picsimlab-esp32`）
- 本地已下载 picsimlab 源码：`D:\work\Esp32Qume\qemu-picsimlab\`
- PICsimLab：https://github.com/lcgamboa/picsimlab
