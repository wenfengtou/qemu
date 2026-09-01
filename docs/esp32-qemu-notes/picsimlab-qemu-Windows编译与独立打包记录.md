# picsimlab-esp32 QEMU Windows 编译与独立打包记录

> 源码：`qemu-picsimlab/`（来自 https://github.com/lcgamboa/qemu 的 `picsimlab-esp32` 分支，QEMU 9.2.2 基线）
> 目标：在 Windows 上编译出**可独立分发**的 `qemu-system-xtensa.exe`，支持 `esp32-picsimlab` 机型与 WiFi/以太网模拟。
> 完成日期：2026-08-30

## 一、结果总览

编译和验证全部完成，最终产物在独立发布目录 [qemu-standalone](computer://d:\work\Esp32Qume\qemu-standalone)：

| 项目 | 结果 |
|---|---|
| QEMU 版本 | 9.2.2（picsimlab-esp32 分支） |
| 编译目标 | `xtensa-softmmu`（仅 Xtensa 体系，含 esp32 / esp32-picsimlab / esp32s3 机型） |
| 主程序 | `qemu-system-xtensa.exe`（约 66 MB） |
| 运行时依赖 | 19 个 MinGW64 DLL（随包分发，目标机无需安装 MSYS2） |
| 固件数据 | 2 个 ESP32 ROM 镜像（`esp32-v3-rom.bin`、`esp32-v3-rom-app.bin`，必须随 exe 分发） |
| 干净环境验证 | PATH 仅含 `C:\Windows\System32` 时正常启动、引导固件、访问外网 |
| 网络实测 | `open_eth` + slirp 用户态网络：固件获取 IP `10.0.2.15`，GET `http://example.com/` 返回 **HTTP 200**（Cloudflare 真实响应） |

可用机型（`qemu-system-xtensa.exe -machine help`）：

```
esp32                Espressif ESP32 machine (default)
esp32-picsimlab      Espressif ESP32 machine (picsimlab)   ← 本分支新增，含 esp32_wifi 网卡
esp32s3              Espressif ESP32S3 machine
```

## 二、编译环境

- 编译平台：Windows + MSYS2（安装在 `D:\msys64`），使用 **MINGW64** 子环境（gcc 14.x POSIX 线程模型）
- 构建系统：meson + ninja（QEMU 9.x 已全面使用 meson）
- 安装的关键 pacman 包：

```bash
pacman -S --needed \
  mingw-w64-x86_64-gcc mingw-w64-x86_64-toolchain \
  mingw-w64-x86_64-glib2 mingw-w64-x86_64-pixman \
  mingw-w64-x86_64-libslirp mingw-w64-x86_64-libgcrypt \
  mingw-w64-x86_64-capstone mingw-w64-x86_64-libtasn1 \
  mingw-w64-x86_64-zstd mingw-w64-x86_64-bzip2 \
  mingw-w64-x86_64-ncurses \
  mingw-w64-x86_64-meson mingw-w64-x86_64-ninja \
  mingw-w64-x86_64-python mingw-w64-x86_64-pkgconf
```

dtc（libfdt）等少量依赖由 QEMU 的 subproject 机制或系统包提供；`keycodemapdb` 等子项目在配置阶段自动拉取。

## 三、为 Windows 编译做的 3 处源码修改

直接 `configure && ninja` 在 Windows 上会遇到三个问题，均已修复：

### 1. 符号链接安装脚本失败（Windows 无管理员/开发者模式权限）

`scripts/symlink-install-tree.py` 在 Windows 上尝试创建符号链接会抛异常，导致构建后处理中断。改为**回退为文件复制**：

```python
if os.name == 'nt':
    # Windows without Developer Mode/admin cannot create
    # symlinks. Copy data files that already exist; skip
    # entries whose source has not been built yet.
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

### 2. slirp 静态链接导致 glib 符号多重定义

MinGW 下静态 libslirp 与 QEMU 自身链接的 glib 符号冲突，链接期报大量 `multiple definition of 'g_*'`。将 slirp 依赖改为动态链接（`meson.build`）：

```meson
slirp_dep = dependency('slirp', required: get_option('slirp'),
                       method: 'pkg-config',
                       static: false)
```

### 3. 两个默认机型触发断言（`Multiple default machines`）

分支合并后 `hw/xtensa/sim.c`（上游自带的 sim 机型）和 `hw/xtensa/esp32.c`（ESP32 机型）都设置了 `mc->is_default = true`，QEMU 启动时在 `find_default_machine()` 触发断言。把 sim 机型改为非默认：

```c
/* hw/xtensa/sim.c */
mc->desc = "sim machine (" XTENSA_DEFAULT_CPU_MODEL ")";
/* esp32 is the default machine in this fork; two defaults trip an
 * assertion in find_default_machine() */
mc->is_default = false;
```

## 四、配置与编译命令

在 **MSYS2 MINGW64 终端**中（不是 UCRT/MSYS 环境）：

```bash
cd /d/work/Esp32Qume/qemu-picsimlab
mkdir -p build && cd build

# 配置：只编译 Xtensa 软模拟目标，启用 slirp 网络与 gcrypt
../configure --target-list=xtensa-softmmu \
             --enable-slirp --enable-gcrypt \
             --disable-werror --disable-docs

# 编译（-j 后接 CPU 核数）
ninja -j8 qemu-system-xtensa.exe
```

实际生效的 meson 选项（见 `build/meson-logs/meson-log.txt`）：

```
-Dslirp=enabled -Dgcrypt=enabled -Dwerror=false -Db_pie=false
-Ddocs=disabled -Dplugins=true --native-file=configs/meson/windows.txt
```

产物：`build/qemu-system-xtensa.exe`。

## 五、功能验证

所有测试均使用本工作区的 ESP-IDF v5.5.5 固件（`wifi_web/build/flash_image.bin`，4MB 合并镜像）。

### 1. 固件引导（blink）

`blink` 例程在 `esp32-picsimlab` 机型上稳定运行，LED 每秒翻转：

```
I (14901) blink: LED OFF
I (15911) blink: LED ON
I (16911) blink: LED OFF
...
```

### 2. 以太网 + 外网访问（open_eth，推荐用法）

```bash
qemu-system-xtensa.exe -M esp32-picsimlab -nographic \
  -drive file=flash_image.bin,if=mtd,format=raw \
  -nic user,model=open_eth
```

串口实测：

```
I (5526) esp_eth.netif.netif_glue: 52:54:00:12:34:56
I (5646) eth: 以太网链路已连接
I (6666) esp_netif_handlers: eth ip: 10.0.2.15, mask: 255.255.255.0, gw: 10.0.2.2
I (7256) web: 响应头: Server = cloudflare
I (7276) web: HTTP 状态码: 200
I (7276) web: 正文片段: <!doctype html><html lang="en"><head><title>Example Domain</title>...
```

固件每 10 秒重复 GET 一次 `example.com`，持续稳定，说明 slirp 用户态网络（NAT + DNS + 出站 TCP）在本 Windows 构建上完全可用。

### 3. esp32_wifi 网卡现状

`esp32-picsimlab` 机型内置本分支新增的 `esp32_wifi` 设备（`hw/misc/esp32_wifi.c`，类型名 `esp32_wifi`），可被 QEMU 识别并挂载：

```bash
qemu-system-xtensa.exe -M esp32-picsimlab -nographic \
  -drive file=flash_image.bin,if=mtd,format=raw \
  -nic user,model=esp32_wifi,net=192.168.4.0/24
```

设备能被实例化、机型也能引导到 `app_main()`，但**用 ESP-IDF v5.5.5 的原生 WiFi 固件会在 WiFi 初始化阶段崩溃**：

```
Guru Meditation Error: Core 0 panic'ed (LoadStorePIFAddrError)
EXCVADDR: 0x3ff69408
```

原因是 picsimlab 的 WiFi 模拟只实现了 PICSimLab 配套固件所需的寄存器子集（面向其虚拟 AP + 特定示例工程），对新版 ESP-IDF `libpp`/WiFi ROM 访问的部分寄存器/内存区域尚未实现。**网络功能当前应使用 `model=open_eth` 路径**；`esp32_wifi` 属于在研特性。

## 六、独立发布目录打包

### 目录内容（`qemu-standalone/`）

| 类别 | 文件 | 说明 |
|---|---|---|
| 主程序 | `qemu-system-xtensa.exe` | 66 MB |
| ROM 数据 | `qemu-bundle\qemu\share\esp32-v3-rom.bin`、`esp32-v3-rom-app.bin` | ESP32 一/二级 ROM，机型初始化时用 `qemu_find_file(QEMU_FILE_TYPE_BIOS, ...)` 加载，**缺失会报 `ROM code binary not found` 并退出** |
| ROM 数据 | `qemu-bundle\qemu\share\esp32c3-rom.bin` | RISC-V 目标用，本包未编译 riscv，保留备用 |
| ROM 数据（冗余备份） | exe 同级目录同样放一份 `esp32-v3-rom*.bin` | 当工作目录恰好是 exe 目录时，QEMU 的「按名直取」逻辑可直接命中 |
| 运行时 DLL | 19 个 | glib/gobject/gio、pixman、libslirp、libgcrypt、capstone、libfdt、zstd、bz2、zlib、iconv、intl、pcre2、ffi、winpthread、ncurses 等 |
| 启动脚本 | `run_esp32.bat` | 封装常用参数，双击/命令行均可（**必须保持纯 ASCII**，见下方坑 2） |

DLL 清单通过 `ldd qemu-system-xtensa.exe` 从 `D:\msys64\mingw64\bin` 逐一提取去重后复制。

### 关键坑 1：ROM 搜索路径是 `qemu-bundle\qemu\share`，不是 exe 同级目录

ESP32 的 ROM（一级引导 ROM）**不是**编译进 exe 的，运行时按 `system/datadir.c` 的 `qemu_find_file()` 搜索：

1. 先按名字相对**当前工作目录**找（`access(name, R_OK)`）；
2. 再遍历重定位数据目录。Windows 重定位逻辑（`util/cutils.c` 的 `get_relocated_path()`）：若 **exe 同级存在 `qemu-bundle` 目录**，则数据目录 = `<exe目录>\qemu-bundle` + 编译期配置路径去掉盘符根。本构建编译期 `CONFIG_QEMU_DATADIR = /qemu/share/`，因此实际搜索 `<exe目录>\qemu-bundle\qemu\share\`；
3. 找不到则回退到编译期写死的 POSIX 路径 `/qemu/share/`（Windows 上必然无效）。

所以正确布局是 `qemu-standalone\qemu-bundle\qemu\share\esp32-v3-rom*.bin`。最初打包时把 ROM 平铺在 exe 旁边，只有「工作目录恰好是 exe 目录」时能侥幸命中；从其他目录（如 `D:\work\Esp32Qume>`）启动就报错：

```
qemu-system-xtensa.exe: Error: -bios argument not set, and ROM code binary not found (1)
```

### 关键坑 2：bat 脚本在 `chcp 65001` 下不能含中文

`run_esp32.bat` 中写中文 REM 注释后，cmd.exe 在 UTF-8 代码页下会错误解析多字节字符，导致后续命令行被截断（现象：`'esp32' is not recognized as an internal or external command`、`'st' is not recognized...`），虽然 QEMU 主命令侥幸完整、仍能启动，但参数行被拆散报错。**bat 内一律使用 ASCII 注释与提示**；固件串口输出的中文日志不受影响（QEMU 直接透传 UTF-8 字节，控制台代码页 65001 正常显示）。

### 干净环境验证方法

把 `qemu-standalone/` 复制到任意目录，在**不含 MSYS2 路径**的环境中运行（模拟裸机）：

```powershell
$env:PATH = 'C:\Windows\System32;C:\Windows'
cd d:\work\Esp32Qume\qemu-standalone
.\qemu-system-xtensa.exe --version                       # QEMU 9.2.2
.\qemu-system-xtensa.exe -machine help | Select-String esp32
.\run_esp32.bat D:\path\to\flash_image.bin
```

实测：版本/机型查询正常，固件引导、DHCP 获取 `10.0.2.15`、访问 `example.com` 返回 HTTP 200，**目标机器无需安装 MSYS2 或任何运行时**。

### 使用方法

```bat
REM 用法：run_esp32.bat <flash镜像.bin> [机型]
run_esp32.bat D:\work\Esp32Qume\wifi_web\build\flash_image.bin
```

等价的完整命令：

```bat
qemu-system-xtensa.exe -M esp32-picsimlab -nographic ^
  -drive file=flash_image.bin,if=mtd,format=raw ^
  -nic user,model=open_eth ^
  -global driver=timer.esp32.timg,property=wdt_disable,value=true
```

- `-nographic`：串口输出到当前控制台（中文日志需 `chcp 65001`，脚本已设置）
- `-nic user,model=open_eth`：slirp 用户态网络，客机 IP 10.0.2.15，宿主机/网关 10.0.2.2，DNS 与出站 HTTP/HTTPS 可用
- `wdt_disable`：关闭定时器看门狗复位，方便长时间观察日志
- flash 镜像为 ESP-IDF 合并镜像（`flash_image.bin`，含 bootloader/分区表/app）

## 七、已知限制

1. **WiFi 模型不完整**：`esp32_wifi` 仅面向 PICSimLab 配套固件；新版 ESP-IDF 原生 WiFi 固件会崩溃，网络请走 `open_eth`。
2. **仅编译了 xtensa-softmmu**：ESP32-C3（RISC-V）不在本 exe 内，`esp32c3-rom.bin` 仅为数据预留。
3. **esp32s3 机型**：源码引用 `esp32s3_rev0_rom.bin`，但分支 `pc-bios/` 未附带该文件，使用 s3 机型需自行补齐 ROM。
4. 动态链接发布：exe 依赖随包 19 个 DLL（GLib/Slirp 等为 LGPL/BSD 许可，分发时请注意保留相应许可声明）。
