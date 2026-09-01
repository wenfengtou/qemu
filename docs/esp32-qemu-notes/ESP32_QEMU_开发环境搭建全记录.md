# ESP32 开发环境搭建 + QEMU 模拟运行全记录

> 从零开始，在 Windows 上完成 ESP-IDF 与 ESP32 QEMU 的下载、安装、配置，编写一个 LED 闪烁（blink）示例，编译并在 QEMU 模拟器中运行，验证「编译 → 运行」全链路。

---

## 0. 环境概览

| 项目 | 版本 / 位置 |
|------|-------------|
| 操作系统 | Windows 10 |
| 终端 | Git Bash（MSYS2/MINGW64） |
| ESP-IDF | v5.5.5（离线安装包） |
| 安装根目录 | `D:\Espressif` |
| QEMU | esp-qemu `esp-develop-9.2.2-20260417`（独立下载） |
| 项目目录 | `D:\work\Esp32Qume` |

---

## 1. 下载

### 1.1 ESP-IDF v5.5.5 离线安装包

选型说明：ESP-IDF v6.0 起官方废弃传统安装器，改用 EIM（Espressif Installation Manager）。v5.5.5 是最后一个成熟的离线安装包版本，自带全套工具链、Python、Git，且与 QEMU 集成最完善，故选用它。

下载地址（二选一）：

```
# 官方 CDN（国内可用，速度约 300-800 KB/s）
https://dl.espressif.com/dl/idf-installer/esp-idf-tools-setup-offline-5.5.5.exe

# GitHub Release（国内直连通常极慢或失败，不推荐）
https://github.com/espressif/idf-installer/releases/download/offline-5.5.5/esp-idf-tools-setup-offline-5.5.5.exe
```

- 大小：约 **1.62 GB**
- 校验：下载完成后确认文件头为 `MZ`（有效的 Windows PE 可执行文件）

### 1.2 ESP32 QEMU（esp-qemu）

Espressif 维护的 QEMU 分支，支持 ESP32（Xtensa 架构）和 RISC-V 系列。按芯片架构分两个包：

| 包 | 支持的芯片 |
|----|-----------|
| `qemu-xtensa` | ESP32 / ESP32-S2 / ESP32-S3 |
| `qemu-riscv32` | ESP32-C3 / C6 / H2 |

> ⚠️ **国内下载坑**：GitHub release 直连基本会卡死在 0 字节（被墙/丢包）。务必使用乐鑫官方国内镜像，把 URL 里的 `github.com` 换成 `dl.espressif.cn/github_assets`。

下载地址（推荐用镜像）：

```
# Xtensa 版（经典 ESP32 必下）
https://dl.espressif.cn/github_assets/espressif/qemu/releases/download/esp-develop-9.2.2-20260417/qemu-xtensa-softmmu-esp_develop_9.2.2_20260417-x86_64-w64-mingw32.tar.xz

# RISC-V 版（ESP32-C3/C6/H2 用，可选）
https://dl.espressif.cn/github_assets/espressif/qemu/releases/download/esp-develop-9.2.2-20260417/qemu-riscv32-softmmu-esp_develop_9.2.2_20260417-x86_64-w64-mingw32.tar.xz
```

解压（两个包都解压到同一目录会自动合并）：

```bash
tar -xJf qemu-xtensa-esp_develop_9.2.2_20260417-win64.tar.xz
tar -xJf qemu-riscv32-esp_develop_9.2.2_20260417-win64.tar.xz
```

解压后结构：

```
qemu/
├── bin/
│   ├── qemu-system-xtensa.exe    # ESP32/S2/S3
│   ├── qemu-system-riscv32.exe   # ESP32-C3/C6/H2
│   └── ...w.exe                  # 带 GUI 窗口的变体
├── share/qemu/                   # 芯片 ROM 文件（esp32-v3-rom.bin 等）
└── lib/ include/
```

验证：`qemu/bin/qemu-system-xtensa.exe --version` 应输出 `QEMU emulator version 9.2.2 (esp_develop_9.2.2_20260417)`。二进制为静态链接，无需额外 DLL。

---

## 2. 安装 ESP-IDF

### 2.1 运行安装器

双击 `esp-idf-tools-setup-offline-5.5.5.exe`，按向导操作：

1. 接受许可协议
2. 选择安装路径（本文使用 `D:\Espressif`）
3. 组件勾选（见 2.2）
4. 开始安装，约 10~20 分钟（离线包已内置工具链，不会重新下载）

### 2.2 组件勾选建议

| 组件 | 建议 | 说明 |
|------|------|------|
| Frameworks → ESP-IDF v5.5.5 | ✅ 必勾 | 核心框架 |
| 开发集成 → PowerShell / 命令提示符 | ✅ 必勾 | 桌面会生成「ESP-IDF 5.5 CMD/PowerShell」入口 |
| 驱动程序（JTAG/USB） | ⬜ 可选 | 只用 QEMU 不烧实物可不勾；烧板子建议勾 |
| Chip Targets → ESP32 | ✅ 必勾 | 本次目标芯片 |
| Chip Targets → 其他（S2/S3/C 系列） | ⬜ 按需 | 不勾可节省数 GB 空间 |

> 注意：「Chip Targets」父复选框为空是正常状态（自定义选择），只需保证 **ESP32** 子项打勾即可。

### 2.3 安装后的目录结构

```
D:\Espressif\
├── frameworks\esp-idf-v5.5.5\        # ESP-IDF 源码框架（IDF_PATH）
├── tools\                             # 工具链（IDF_TOOLS_PATH）
│   ├── xtensa-esp-elf\esp-14.2.0_20260121\xtensa-esp-elf\bin\  # 编译器
│   ├── cmake\3.30.2\bin\
│   ├── ninja\1.12.1\
│   ├── idf-git\2.44.0\cmd\
│   ├── esp-rom-elfs\20241011\         # ROM ELF（调试用）
│   └── ...
├── python_env\idf5.5_py3.11_env\      # Python 虚拟环境
│   └── Scripts\python.exe
├── dist\ / esp_idf.json / idf-env.exe / Initialize-Idf.ps1
```

---

## 3. 编写 LED blink demo

### 3.1 项目结构

```
blink/
├── CMakeLists.txt          # 顶层构建脚本
└── main/
    ├── CMakeLists.txt      # 组件构建脚本
    └── blink.c             # 主程序
```

### 3.2 源码

**`blink/CMakeLists.txt`**（顶层）：

```cmake
cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(blink)
```

**`blink/main/CMakeLists.txt`**：

```cmake
idf_component_register(SRCS "blink.c"
                       INCLUDE_DIRS ".")
```

**`blink/main/blink.c`**：

```c
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_log.h"

#define BLINK_GPIO  GPIO_NUM_2   // 板载 LED 引脚（多数 ESP32 开发板为 GPIO2）
#define BLINK_DELAY 1000         // 翻转间隔 ms

static const char *TAG = "blink";

void app_main(void)
{
    ESP_LOGI(TAG, "LED blink demo 启动，GPIO%d", BLINK_GPIO);
    gpio_reset_pin(BLINK_GPIO);
    gpio_set_direction(BLINK_GPIO, GPIO_MODE_OUTPUT);

    while (1) {
        ESP_LOGI(TAG, "LED ON");
        gpio_set_level(BLINK_GPIO, 1);
        vTaskDelay(pdMS_TO_TICKS(BLINK_DELAY));

        ESP_LOGI(TAG, "LED OFF");
        gpio_set_level(BLINK_GPIO, 0);
        vTaskDelay(pdMS_TO_TICKS(BLINK_DELAY));
    }
}
```

---

## 4. 编译

### 4.1 关键坑：Git Bash 的 MSYS 限制 ⚠️

ESP-IDF v5.5 在 Git Bash（MSYS2/MINGW64）环境下**无法直接运行**。原因：

- `export.sh` / `activate.py` / `idf.py` / `idf_tools.py` 都会检测 `MSYSTEM` 环境变量；
- Git Bash 会**强制注入** `MSYSTEM=MINGW64`，且 `unset MSYSTEM`、`env -u MSYSTEM` 都无效（环境变量会被重新注入）；
- 一旦检测到 MSYS 环境，idf.py 直接打印警告后退出（根本不执行 `main()`）。

**解决方案**：写一个启动器脚本，在 Python 内存里移除 `MSYSTEM`，然后绕过 `idf.py` 的 `__main__` 检查，直接调用 `idf.main()`。

**`.idf_wrapper.py`**（放在项目根目录）：

```python
import os
import sys

# 关键：移除 MSYSTEM，避免 idf.py 及其子进程检测到 MSYS 环境后拒绝运行
os.environ.pop('MSYSTEM', None)

sys.path.insert(0, r'D:/Espressif/frameworks/esp-idf-v5.5.5/tools')

import idf  # noqa: E402

idf.main(sys.argv[1:])
```

> 原理：`idf.main()` 接收 `sys.argv[1:]`，等价于 `idf.py <参数>`。移除 `MSYSTEM` 后，`idf.py` 内部 `subprocess` 调用的 `idf_tools.py` 也不会再触发 MSYS 检测。

### 4.2 环境变量

不用 `export.sh`（它同样被 MSYS 限制拦截），手动设置：

```bash
export IDF_PATH="D:/Espressif/frameworks/esp-idf-v5.5.5"
export IDF_TOOLS_PATH="D:/Espressif"
export IDF_PYTHON_ENV_PATH="D:/Espressif/python_env/idf5.5_py3.11_env"
export ESP_ROM_ELF_DIR="D:/Espressif/tools/esp-rom-elfs/20241011/"
export PYTHONDONTWRITEBYTECODE=1   # 减少 Python 缓存写入

export PATH="/d/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20260121/xtensa-esp-elf/bin:/d/Espressif/tools/cmake/3.30.2/bin:/d/Espressif/tools/ninja/1.12.1:/d/Espressif/tools/idf-git/2.44.0/cmd:/d/Espressif/python_env/idf5.5_py3.11_env/Scripts:$PATH"
```

### 4.3 编译命令

```bash
cd "D:/work/Esp32Qume/blink"

# 1) 设置目标芯片（首次，生成 sdkconfig）
"D:/Espressif/python_env/idf5.5_py3.11_env/Scripts/python.exe" "D:/work/Esp32Qume/.idf_wrapper.py" set-target esp32

# 2) 编译
"D:/Espressif/python_env/idf5.5_py3.11_env/Scripts/python.exe" "D:/work/Esp32Qume/.idf_wrapper.py" build
```

> ⚠️ **沙箱权限**：编译会写 `D:\Espressif\.git\index.lock`（git 子模块检查）和 `__pycache__`，在受限沙箱里会被拦截。需以**非沙箱模式**运行（在 AI 助手里即 `dangerouslyDisableSandbox`，或直接在你自己的「ESP-IDF 5.5 PowerShell」里手动执行上述命令）。

### 4.4 编译成功的标志

```
Project build complete. To flash, run:
 ...
Generated D:/work/Esp32Qume/blink/build/blink.bin
```

生成产物：

| 文件 | 说明 |
|------|------|
| `build/blink.bin` | 应用固件 |
| `build/bootloader/bootloader.bin` | 引导程序 |
| `build/partition_table/partition-table.bin` | 分区表 |

---

## 5. 在 QEMU 中运行

### 5.1 合并 flash 镜像

ESP32 从 flash 启动，QEMU 需要一个包含 bootloader + 分区表 + app 的完整镜像：

```bash
cd "D:/work/Esp32Qume/blink/build"

"D:/Espressif/python_env/idf5.5_py3.11_env/Scripts/esptool.exe" --chip esp32 merge_bin \
  -o flash_image.bin \
  0x1000  bootloader/bootloader.bin \
  0x8000  partition_table/partition-table.bin \
  0x10000 blink.bin
```

### 5.2 填充到 2MB ⚠️

esp-qemu 的 ESP32 机器**只接受 2/4/8/16 MB 的 flash 镜像**。合并出的镜像只有约 228KB，会报错：

```
Error: only 2, 4, 8, 16 MB flash images are supported
```

用 Python 填充 `0xFF` 到 2MB（与 sdkconfig 的 `flash_size 2MB` 一致）：

```python
import pathlib
p = pathlib.Path('flash_image.bin')
data = p.read_bytes()
data += b'\xff' * (2 * 1024 * 1024 - len(data))
p.write_bytes(data)
```

### 5.3 运行命令

```bash
cd "D:/work/Esp32Qume/qemu/bin"

qemu-system-xtensa.exe -M esp32 -nographic \
  -drive file="D:/work/Esp32Qume/blink/build/flash_image.bin",if=mtd,format=raw
```

参数说明：

| 参数 | 含义 |
|------|------|
| `-M esp32` | 指定 ESP32 机器 |
| `-nographic` | 无图形窗口，串口输出到当前终端 |
| `-drive file=...,if=mtd` | 加载 flash 镜像 |

ROM 文件（`esp32-v3-rom.bin` 等）会自动从 `qemu/share/qemu/` 加载。

### 5.4 运行结果

```
ets Jul 29 2019 12:21:46
rst:0x1 (POWERON_RESET),boot:0x12 (SPI_FAST_FLASH_BOOT)
...
I (905) boot: ESP-IDF v5.5.5 2nd stage bootloader
I (1818) boot: Loaded app from partition at offset 0x10000
I (3598) blink: LED blink demo 启动，GPIO2
I (3598) blink: LED ON
I (4608) blink: LED OFF
I (5608) blink: LED ON
I (6608) blink: LED OFF
...（每秒翻转，无限循环）
```

看到 `LED ON/OFF` 循环即代表整条「编写 → 编译 → 模拟运行」链路打通。退出按 `Ctrl+A` 然后 `X`，或直接关窗口。

---

## 6. 一键运行脚本

`D:\work\Esp32Qume\run_qemu.bat`（双击即可弹出窗口实时查看 LED 日志）：

```bat
@echo off
chcp 65001 >nul
echo ==============================================
echo   ESP32 blink demo - QEMU simulator
echo   LED ON/OFF logs will stream below (1s cycle)
echo   Close this window to quit
echo ==============================================
cd /d D:\work\Esp32Qume\qemu\bin
qemu-system-xtensa.exe -M esp32 -nographic -drive file=D:\work\Esp32Qume\blink\build\flash_image.bin,if=mtd,format=raw
```

---

## 7. 常见问题 FAQ

### Q1：idf.py 报 `MSys/Mingw is no longer supported`
Git Bash 环境下 ESP-IDF 的 MSYS 检测。用 `.idf_wrapper.py` 启动器（移除 `MSYSTEM` + 直接调 `idf.main()`），或改用「ESP-IDF 5.5 PowerShell」。

### Q2：编译被沙箱拦截（`Blocked: .git/index.lock`）
编译需要访问 ESP-IDF 安装目录（git 子模块检查、Python 缓存）。用非沙箱模式运行，或在官方 PowerShell 里手动执行。

### Q3：QEMU 报 `only 2, 4, 8, 16 MB flash images are supported`
flash 镜像太小。合并后用 `0xFF` 填充到 2/4/8/16MB。

### Q4：GitHub 下载 QEMU 卡在 0 字节
用乐鑫国内镜像 `https://dl.espressif.cn/github_assets/...` 替代 `https://github.com/...`。

### Q5：能不能跑 Arduino 代码？
esp-qemu 面向 ESP-IDF 固件。Arduino for ESP32 底层虽是 ESP-IDF，但需要手动合并固件且外设模拟有限，不推荐。想跑 Arduino 建议用 Wokwi 或真机。

---

## 附录：完整命令速查

```bash
# ===== 编译 =====
export IDF_PATH="D:/Espressif/frameworks/esp-idf-v5.5.5"
export IDF_TOOLS_PATH="D:/Espressif"
export IDF_PYTHON_ENV_PATH="D:/Espressif/python_env/idf5.5_py3.11_env"
export ESP_ROM_ELF_DIR="D:/Espressif/tools/esp-rom-elfs/20241011/"
export PATH="/d/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20260121/xtensa-esp-elf/bin:/d/Espressif/tools/cmake/3.30.2/bin:/d/Espressif/tools/ninja/1.12.1:/d/Espressif/tools/idf-git/2.44.0/cmd:/d/Espressif/python_env/idf5.5_py3.11_env/Scripts:$PATH"

PY="D:/Espressif/python_env/idf5.5_py3.11_env/Scripts/python.exe"
WRAP="D:/work/Esp32Qume/.idf_wrapper.py"

cd "D:/work/Esp32Qume/blink"
"$PY" "$WRAP" set-target esp32   # 首次
"$PY" "$WRAP" build              # 编译

# ===== 合并 + 填充 flash 镜像 =====
cd "D:/work/Esp32Qume/blink/build"
"D:/Espressif/python_env/idf5.5_py3.11_env/Scripts/esptool.exe" --chip esp32 merge_bin \
  -o flash_image.bin 0x1000 bootloader/bootloader.bin 0x8000 partition_table/partition-table.bin 0x10000 blink.bin
# 然后用 Python 把 flash_image.bin 填充到 2MB（0xFF）

# ===== 运行 QEMU =====
cd "D:/work/Esp32Qume/qemu/bin"
./qemu-system-xtensa.exe -M esp32 -nographic -drive file="D:/work/Esp32Qume/blink/build/flash_image.bin",if=mtd,format=raw
```
