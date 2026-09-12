# picsimlab-esp32 QEMU 动态库（libqemu-xtensa.dll）编译与部署记录

> 源码：fork 仓库 `D:\work\Esp32Qume\myself\qemu`（来自 <https://github.com/qianmayi/qemu> ，上游为 lcgamboa/qemu 的 `picsimlab-esp32` 分支，QEMU 9.2.2 基线）
> 目标：编译出 **PICSimLab 可直接 LoadLibrary 的动态库** `libqemu-xtensa.dll`，替代 exe 形态，供图形化仿真调用（GPIO 回调、UART、定时器等）。
> 完成日期：2026-09-05（此前已有 exe 形态的编译记录，见同目录 `picsimlab-qemu-Windows编译与独立打包记录.md`）

## 一、结果总览

| 项目      | 结果                                                      |
| ------- | ------------------------------------------------------- |
| QEMU 版本 | 9.2.2（picsimlab-esp32 分支，fork 仓库）                       |
| 编译目标    | `xtensa-softmmu`（仅 Xtensa，含 esp32-picsimlab 机型）         |
| 产物      | `build/libqemu-xtensa.dll`（约 68.5 MB，2026-09-05 21:11）  |
| 部署位置    | `PICSimLab\picsimlab_win64\lib\qemu\libqemu-xtensa.dll` |
| 导出符号    | PICSimLab 0.9.2 所需全部符号（实测 39 个关键符号，见附录）                 |
| 验证      | PICSimLab 加载成功、GPIO 演示固件正常运行（LED 闪烁 + 按键控制）             |

## 二、为什么需要 DLL 而不是 exe

PICSimLab 的 ESP32 仿真后端（`src/sim_backend/bsim_qemu.cc`）通过 `LoadLibraryA` 动态加载 QEMU 库，再 `GetProcAddress` 按名解析符号：

```cpp
std::string fullpath = std::string(dpath) + "/lib/qemu/" + path + ".dll";
HMODULE handle = LoadLibraryA((const char*)fullpath.c_str());
```

加载路径写死为 **`<picsimlab.exe所在目录>\lib\qemu\`**。所以 DLL 必须部署到
`PICSimLab\picsimlab_win64\lib\qemu\libqemu-xtensa.dll`（picsimlab.exe 在该目录）。

QEMU 自身的 `qemu_init()` 入口在 `system/vl.c`，`qemu_main_loop()` 在 `system/cpus.c`。
exe 形态用 `main()` 调 `qemu_init`；DLL 形态去掉 `main()` 目标文件（`system_main.c.o`），
把同一套对象以 `-shared` 重链成库，PICSimLab 自己起线程调 `qemu_init`。

## 三、源码修改

### 1. system/cpus.c：iothread 锁兼容别名（必须）

QEMU 9.x 把旧的 iothread 锁重命名为 BQL（Big QEMU Lock）：`bql_lock_impl()` / `bql_unlock()`。
而预编译的 PICSimLab 0.9.2（241005）按旧名字解析符号，加载时报：

```
Qemu lib Lost symbol: qemu_mutex_lock_iothread_impl
```

在 `system/cpus.c` 中补充两个兼容别名（同时保留 `bql_*` 原名导出）：

```c
void qemu_mutex_lock_iothread_impl(const char *file, int line)
{
    bql_lock_impl(file, line);
}

void qemu_mutex_unlock_iothread(void)
{
    bql_unlock();
}
```

### 2. 临时调试日志（已移除，未入库）

排查 PICSimLab 未调用 `qemu_init` 的问题时，曾在 `system/runstate.c`、`system/vl.c`
临时硬编码写日志（`qemu_dbg.log`，含 Windows 绝对路径）用于确认初始化流程。
定位完成后已从源码删除，仅存在于 21:11 那次 DLL 产物中。

## 四、编译步骤（Windows + MSYS2 MINGW64）

### 1. 环境

- MSYS2 **MINGW64** 终端（`D:\msys64`），gcc 14.x

- 依赖包与 exe 编译一致：glib2、pixman、libslirp、libgcrypt、capstone、zstd 等（见 exe 编译记录）

### 2. configure（build 目录）

```bash
cd /d/work/Esp32Qume/myself/qemu
mkdir -p build && cd build
../configure --target-list=xtensa-softmmu \
             --enable-debug --enable-gcrypt --enable-slirp \
             --disable-werror --disable-docs
```

实际生效选项（`build/meson-info/intro-buildoptions.json` 核对）：`debug=enabled`、
`gcrypt=enabled`、`slirp=enabled`、`werror=false`、`docs=disabled`、`tcg=enabled`。
Windows PE 目标天然 PIC，无需 `-fPIC`（上游 Linux 脚本里才需要）。

### 3. 先正常构建 exe

```bash
ninja -j8 qemu-system-xtensa.exe
```

### 4. 提取链接命令，改为共享库重链

原理（沿用上游 `build_libqemu-esp32.sh` 的思路，Windows 手工适配）：

1. `ninja -v -d keeprsp` 输出中取**最后一条链接命令**（含全部对象与库）；
2. 从中**剔除** **`system_main.c.o`**（即 `main()`，DLL 不需要入口）；
3. 把 `-o qemu-system-xtensa.exe` 改为 **`-shared -o libqemu-xtensa.dll`**；
4. 用同一组对象重新链接。

最终链接命令保存在 `build/libqemu-xtensa.rsp`，开头为：

```
-shared -o libqemu-xtensa.dll version.rc_version.o libcommon.a.p/gdbstub_syscalls.c.obj ...
```

注意：

- rsp 里含 `version.rc_version.o`（Windows 版本资源），保留即可；

- 上游脚本用 `sed` 处理路径，Windows 下曾出现路径中 `$` 等特殊字符被误解析的问题，
  建议**直接人工检查/构造 rsp**，不要完全依赖脚本的 sed 链。

### 5. 符号导出机制（无需 .def）

MinGW PE 目标链接 `-shared` 时，若无 `.def` / `__declspec(dllexport)`，ld **默认导出全部全局符号**，
因此 `GetProcAddress` 能按名取到所有 PICSimLab 需要的符号。实测导出表含 7000+ 符号
（含 glib 等依赖符号的合并导出，属正常现象，不影响使用）。

### 6. 两次构建的说明

| 尝试  | 目录           | 大小           | 时间          | 说明                |
| --- | ------------ | ------------ | ----------- | ----------------- |
| 第一次 | `build-dll/` | 68,866,837 B | 09-05 11:51 | 早期适配尝试            |
| 最终  | `build/`     | 68,519,222 B | 09-05 21:11 | 含 cpus.c 别名修复，已部署 |

## 五、部署到 PICSimLab

### 1. 复制 DLL

```powershell
Copy-Item D:\work\Esp32Qume\myself\qemu\build\libqemu-xtensa.dll `
          D:\work\Esp32Qume\PICSimLab\picsimlab_win64\lib\qemu\libqemu-xtensa.dll -Force
```

PICSimLab 运行中会占用文件，部署时可先复制为 `.new` 再改名。

### 2. 依赖 DLL 冲突修复（关键坑）

PICSimLab exe 根目录曾自带一批**旧版本** MinGW DLL（`libstdc++-6.dll`、
`libglib-2.0-0.dll` 等 8 个），Windows 的 DLL 搜索顺序会优先命中 exe 根目录，
导致 QEMU DLL 加载后依赖解析错误（报 "Error loading libqemu-xtensa"）。

修复：

- 将 exe 根目录冲突的 8 个旧 DLL **替换为 MSYS2 MINGW64 新版**；

- 并把 `PICSimLab\picsimlab_win64\lib\qemu` 加入系统 `PATH`，保证按正确顺序命中。

### 3. keymap 缺失修复

`qemu_init()` 初始化显示子系统时需要 `keymaps/en-us`，PICSimLab 的 fw 目录缺失该文件，
报错 `could not read keymap file: 'en-us'`。

修复：从 QEMU 源码复制：

```powershell
Copy-Item D:\work\Esp32Qume\myself\qemu\pc-bios\keymaps\en-us `
          D:\work\Esp32Qume\PICSimLab\picsimlab_win64\lib\qemu\fw\keymaps\ -Force
```

## 六、验证方法

### 1. 符号检查

```powershell
& D:\msys64\mingw64\bin\objdump.exe -p libqemu-xtensa.dll | Select-String "qemu_init|qemu_picsimlab|qemu_mutex_lock_iothread"
```

### 2. 加载验证

命令行启动 PICSimLab 加载 ESP32-DevKitC 板子，无 "Error loading libqemu-xtensa" 弹窗即加载成功；
可用任务管理器确认进程内已装入该 DLL。

### 3. 功能验证

GPIO 演示固件（`picsimlab_gpio_demo.ino`，GPIO2 控制 LED 闪烁、GPIO0 检测 BOOT 按键）：
PICSimLab 图形界面中 **LED 实时闪烁、按键按下时 LED 常亮**，说明回调链路完整：
固件 → QEMU 执行 → `picsimlab_write_pin` 回调 → 电路组件状态更新。

## 七、已知限制

1. **调试日志代码未进仓库**：21:11 的 DLL 含临时调试代码，源码已删除；如重新编译，产物不再写 `qemu_dbg.log`（功能无差异）。
2. **WiFi 模型不完整**：`esp32_wifi` 仅支持 PICSimLab 配套固件，新版 ESP-IDF 原生 WiFi 固件会崩溃；网络请走 `open_eth`。
3. **仅编译 xtensa-softmmu**：不含 riscv32（ESP32-C3 需另行编译 `libqemu-riscv32.dll`，上游脚本已含对应流程）。

## 附录：实测导出符号（objdump -p，关键 39 个命中）

```
bql_lock_impl / bql_locked / bql_unlock
qemu_cleanup / qemu_init / qemu_main_loop / qemu_clock_get_ns
qemu_mutex_lock_iothread_impl / qemu_mutex_unlock_iothread   ← 新增兼容别名
qemu_picsimlab_flash_dump / qemu_picsimlab_get_TIOCM
qemu_picsimlab_get_internals / qemu_picsimlab_register_callbacks
qemu_picsimlab_set_apin / qemu_picsimlab_set_pin / qemu_picsimlab_uart_receive
qmp_cont / qmp_memsave / qmp_pmemsave / qmp_quit / qmp_stop / qmp_system_reset
timer_init_full / timer_mod_ns
```

