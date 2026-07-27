"""Desktop Pet 应用入口（平台化）。

启动流程：
1. 解析命令行参数（argparse，支持子命令 add / list 与启动标志 verbose / hidden）
2. 配置日志
3. 分流：
   - ``add`` 子命令：通过 HTTP API 创建新桌宠实例
   - ``list`` 子命令：通过 HTTP API 列出运行中实例
   - 无子命令：启动 GUI（创建 QApplication → PetPlatform → 恢复实例 → API 服务器 → 系统托盘）

入口点：
- ``uv run python -m desktop_pet`` → 本模块
- ``uv run desktop-pet`` → 本模块的 ``main``
- PyInstaller 打包时通过项目根目录的 ``main.py`` 调用本模块的 ``main``

CLI 子命令：
- ``desktop-pet add --package <name> [--x N] [--y N]``：新增运行桌宠（需主进程已启动）
- ``desktop-pet list``：列出运行中实例（需主进程已启动）
- ``desktop-pet``（无子命令）：启动 GUI
"""
import argparse
import asyncio
import logging
import sys
import threading

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from .cli_client import CliError, check_main_process, get_api_base

logger = logging.getLogger(__name__)

# 模块级单例：设置中心对话框（避免重复创建）
_settings_center_instance = None


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Reduce noise from third-party libraries
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


def _build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    - 主 parser 含 ``--verbose`` / ``-v`` 与 ``--hidden`` / ``-H``（注意短选项为 -H，
      避免与 argparse 默认的 -h help 冲突）
    - 子命令 ``add``：``--package`` / ``-p``（必填）、``--x``、``--y``
    - 子命令 ``list``：无参数
    - 无子命令时 ``args.command`` 为 None，走 GUI 启动流程（向后兼容）
    """
    parser = argparse.ArgumentParser(
        prog="desktop-pet",
        description="桌面宠物平台 - 多实例运行与远程控制",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="启用 DEBUG 级别日志"
    )
    parser.add_argument(
        "--hidden",
        "-H",
        action="store_true",
        help="启动时隐藏到系统托盘（仅 GUI 模式生效）",
    )

    subparsers = parser.add_subparsers(dest="command")

    # add 子命令
    add_parser = subparsers.add_parser("add", help="新增运行桌宠实例（需主进程已启动）")
    add_parser.add_argument(
        "--package", "-p", required=True, help="宠物资源包名（如 default）"
    )
    add_parser.add_argument(
        "--x", type=int, default=None, help="初始 X 坐标（省略则用包默认值）"
    )
    add_parser.add_argument(
        "--y", type=int, default=None, help="初始 Y 坐标（省略则用包默认值）"
    )

    # list 子命令
    subparsers.add_parser("list", help="列出运行中桌宠实例（需主进程已启动）")

    # remove 子命令
    remove_parser = subparsers.add_parser(
        "remove", help="关闭并销毁指定桌宠实例（需主进程已启动）"
    )
    remove_parser.add_argument("pet_id", help="目标桌宠实例 ID")
    remove_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="跳过确认提示，直接销毁",
    )

    # animate 子命令
    animate_parser = subparsers.add_parser(
        "animate", help="播放指定动画（需主进程已启动）"
    )
    animate_parser.add_argument("pet_id", help="目标桌宠实例 ID")
    animate_parser.add_argument(
        "--name", "-n", required=True, help="动画名称（如 sit / walk / sleep）"
    )

    # walk 子命令
    walk_parser = subparsers.add_parser(
        "walk", help="行走动画（需主进程已启动）"
    )
    walk_parser.add_argument("pet_id", help="目标桌宠实例 ID")
    walk_parser.add_argument(
        "--direction",
        "-d",
        required=True,
        choices=["left", "right"],
        help="行走方向",
    )

    # move 子命令（三种模式互斥）
    move_parser = subparsers.add_parser(
        "move", help="移动桌宠（需主进程已启动）"
    )
    move_parser.add_argument("pet_id", help="目标桌宠实例 ID")
    move_mode = move_parser.add_mutually_exclusive_group(required=True)
    move_mode.add_argument(
        "--xy",
        nargs=2,
        type=int,
        metavar=("X", "Y"),
        help="绝对坐标，如 --xy 500 300",
    )
    move_mode.add_argument(
        "--delta",
        nargs=2,
        type=int,
        metavar=("DX", "DY"),
        help="相对移动，如 --delta 50 0",
    )
    move_mode.add_argument(
        "--edge",
        choices=["left", "right"],
        help="移到屏幕边缘",
    )
    move_parser.add_argument(
        "--screen",
        type=int,
        default=None,
        help="目标屏幕索引（仅 --xy / --edge 适用）",
    )

    # animations 子命令
    animations_parser = subparsers.add_parser(
        "animations", help="列出指定桌宠的可用动画"
    )
    animations_parser.add_argument("pet_id", help="目标桌宠实例 ID")

    # bubble 子命令（显示/隐藏文字气泡）
    bubble_parser = subparsers.add_parser(
        "bubble", help="显示或隐藏文字气泡（需主进程已启动）"
    )
    bubble_parser.add_argument("pet_id", help="目标桌宠实例 ID")
    bubble_mode = bubble_parser.add_mutually_exclusive_group(required=True)
    bubble_mode.add_argument(
        "--text", "-t", help="气泡文本内容（显示气泡）"
    )
    bubble_mode.add_argument(
        "--hide", action="store_true", help="隐藏气泡"
    )
    bubble_parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="显示时长（毫秒），0=持续显示（默认），>0=N 毫秒后自动隐藏",
    )

    return parser


def main():
    """Main entry point for the application."""
    parser = _build_parser()
    args = parser.parse_args()

    setup_logging(args.verbose)

    try:
        if args.command == "add":
            _run_add(args)
        elif args.command == "list":
            _run_list(args)
        elif args.command == "remove":
            _run_remove(args)
        elif args.command == "animate":
            _run_animate(args)
        elif args.command == "walk":
            _run_walk(args)
        elif args.command == "move":
            _run_move(args)
        elif args.command == "animations":
            _run_animations(args)
        elif args.command == "bubble":
            _run_bubble(args)
        else:
            _run_gui(args)
    except CliError as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)


# ----------------------------------------------------------------------
# 子命令实现
# ----------------------------------------------------------------------
def _run_add(args: argparse.Namespace) -> None:
    """``desktop-pet add`` 子命令：通过 HTTP API 创建新桌宠实例。"""
    from . import cli_client

    api_base = get_api_base()
    if not check_main_process(api_base):
        raise CliError("主进程未运行，请先执行 desktop-pet 启动主应用")

    result = cli_client.add_instance(api_base, args.package, args.x, args.y)
    pet_id = result.get("pet_id", "?")
    package = result.get("package", args.package)
    position = result.get("position", {})
    print(
        f"已创建桌宠实例 pet_id={pet_id} package={package} position={position}"
    )


def _run_list(args: argparse.Namespace) -> None:
    """``desktop-pet list`` 子命令：通过 HTTP API 列出运行中实例。"""
    from . import cli_client

    api_base = get_api_base()
    if not check_main_process(api_base):
        raise CliError("主进程未运行，请先执行 desktop-pet 启动主应用")

    instances = cli_client.list_instances(api_base)
    if not instances:
        print("当前没有运行中的桌宠实例")
        return

    # 表格输出：pet_id | package | primary | position
    print(f"{'pet_id':<10} {'package':<12} {'primary':<8} position")
    print("-" * 50)
    for inst in instances:
        pet_id = inst.get("pet_id", "?")
        package = inst.get("package", "?")
        primary = "是" if inst.get("primary") else "否"
        position = inst.get("position", {})
        pos_str = f"({position.get('x', '?')}, {position.get('y', '?')})"
        print(f"{pet_id:<10} {package:<12} {primary:<8} {pos_str}")


def _run_remove(args: argparse.Namespace) -> None:
    """``desktop-pet remove <pet_id> [--yes]`` 子命令：销毁指定桌宠实例。

    默认会要求用户输入 ``y`` 确认；传 ``--yes`` / ``-y`` 跳过确认。
    """
    from . import cli_client

    api_base = get_api_base()
    if not check_main_process(api_base):
        raise CliError("主进程未运行，请先执行 desktop-pet 启动主应用")

    if not args.yes:
        confirm = input(f"确定要销毁桌宠实例 {args.pet_id} 吗？(y/N) ").strip().lower()
        if confirm != "y":
            print("已取消")
            return

    cli_client.remove_instance(api_base, args.pet_id)
    print(f"已销毁桌宠实例 pet_id={args.pet_id}")


def _run_animate(args: argparse.Namespace) -> None:
    """``desktop-pet animate <pet_id> --name <action>`` 子命令：播放指定动画。"""
    from . import cli_client

    api_base = get_api_base()
    if not check_main_process(api_base):
        raise CliError("主进程未运行，请先执行 desktop-pet 启动主应用")

    result = cli_client.play_animation(api_base, args.pet_id, args.name)
    if not result.get("success", False):
        raise CliError(f"播放动画失败：{result.get('error', '未知错误')}")
    print(f"已播放动画 {args.name} -> pet {args.pet_id}")


def _run_walk(args: argparse.Namespace) -> None:
    """``desktop-pet walk <pet_id> --direction <left|right>`` 子命令：行走动画。"""
    from . import cli_client

    api_base = get_api_base()
    if not check_main_process(api_base):
        raise CliError("主进程未运行，请先执行 desktop-pet 启动主应用")

    result = cli_client.walk_pet(api_base, args.pet_id, args.direction)
    if not result.get("success", False):
        raise CliError(f"行走失败：{result.get('error', '未知错误')}")
    print(f"已行走 {args.direction} -> pet {args.pet_id}")


def _run_move(args: argparse.Namespace) -> None:
    """``desktop-pet move <pet_id> (--xy X Y | --delta DX DY | --edge left|right) [--screen N]``"""
    from . import cli_client

    api_base = get_api_base()
    if not check_main_process(api_base):
        raise CliError("主进程未运行，请先执行 desktop-pet 启动主应用")

    if args.xy is not None:
        x, y = args.xy
        result = cli_client.move_to(api_base, args.pet_id, x, y, args.screen)
        action = f"移动至 ({x}, {y})"
    elif args.delta is not None:
        dx, dy = args.delta
        result = cli_client.move_by(api_base, args.pet_id, dx, dy)
        action = f"相对移动 ({dx}, {dy})"
    else:  # args.edge
        result = cli_client.move_edge(api_base, args.pet_id, args.edge, args.screen)
        action = f"移至 {args.edge} 边缘"

    if not result.get("success", False):
        raise CliError(f"移动失败：{result.get('error', '未知错误')}")
    screen_str = f" screen={args.screen}" if args.screen is not None else ""
    print(f"已{action} -> pet {args.pet_id}{screen_str}")


def _run_animations(args: argparse.Namespace) -> None:
    """``desktop-pet animations <pet_id>`` 子命令：列出指定桌宠可用动画。"""
    from . import cli_client

    api_base = get_api_base()
    if not check_main_process(api_base):
        raise CliError("主进程未运行，请先执行 desktop-pet 启动主应用")

    animations = cli_client.list_animations(api_base, args.pet_id)
    if not animations:
        print(f"pet {args.pet_id} 无可用动画")
        return
    print(f"pet {args.pet_id} 可用动画：")
    for name in animations:
        print(f"  - {name}")


def _run_bubble(args: argparse.Namespace) -> None:
    """``desktop-pet bubble <pet_id> (--text "..." [--duration N] | --hide)``"""
    from . import cli_client

    api_base = get_api_base()
    if not check_main_process(api_base):
        raise CliError("主进程未运行，请先执行 desktop-pet 启动主应用")

    if args.hide:
        cli_client.hide_bubble(api_base, args.pet_id)
        print(f"已隐藏气泡 -> pet {args.pet_id}")
    else:
        result = cli_client.show_bubble(
            api_base, args.pet_id, args.text, args.duration
        )
        if not result.get("success", False):
            raise CliError(f"显示气泡失败：{result.get('error', '未知错误')}")
        dur_str = f"，持续 {args.duration}ms" if args.duration > 0 else "，持续显示"
        print(f"已显示气泡 -> pet {args.pet_id}{dur_str}")


# ----------------------------------------------------------------------
# GUI 启动（原 main() 逻辑）
# ----------------------------------------------------------------------
def _run_gui(args: argparse.Namespace) -> None:
    """启动 GUI 主应用（原 main() 逻辑）。"""
    start_hidden = args.hidden

    # 延迟导入：避免在 setup_logging 之前触发第三方库日志
    from .pet_platform import PetPlatform
    from .pet import DesktopPet
    from .api_server import ApiServer
    from .system_tray import SystemTrayIcon
    from .setup_wizard import SetupWizard
    from .pet_loader import PetLoader
    from .ui_style import global_app_stylesheet

    app = QApplication(sys.argv)
    app.setApplicationName("Desktop Pet")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(global_app_stylesheet())

    # 首次运行检查：若无宠物资源，显示向导
    pet_loader = PetLoader()
    available_pets = pet_loader.scan_pets()
    if not available_pets:
        wizard = SetupWizard()
        if not wizard.exec():
            sys.exit(0)
        # 向导完成后重新扫描
        available_pets = pet_loader.scan_pets()
        if not available_pets:
            sys.exit(0)

    # 创建平台，注入 widget 工厂
    platform = PetPlatform()

    def widget_factory(pet_id, instance_config, pet_package):
        """创建 DesktopPet 实例 widget。"""
        return DesktopPet(instance_config, pet_package, platform)

    platform._widget_factory = widget_factory

    # 启动平台（迁移 + 恢复实例 + 创建 ScreenManager + 创建 widgets）
    platform.start()

    # 若无实例（首次启动且无 legacy 迁移），创建默认 primary 实例
    if not platform.list_instances():
        first_package = available_pets[0].name
        platform.create_instance(first_package)
        # 标记为 primary
        configs = platform.list_instances()
        if configs:
            platform.update_instance_config(configs[0].pet_id, {"primary": True})

    # API server is always platform-owned so settings can enable it at runtime.
    api_config = platform.global_config.config.get("api", {})
    api_server = ApiServer(platform)
    api_server.configure(
        api_config.get("host", "127.0.0.1"),
        api_config.get("port", 8080),
    )
    api_server.set_allowed_ips(
        api_config.get("allowed_ips", ["127.0.0.1", "::1"])
    )
    api_server.set_trust_proxy_headers(api_config.get("trust_proxy_headers", False))
    mcp_config = platform.global_config.config.get("mcp", {})
    api_server.set_openclaw_config(
        mcp_config.get("openclaw_webhook_url", ""),
        mcp_config.get("openclaw_peer", ""),
        mcp_config.get("openclaw_secret_token", ""),
        mcp_config.get("openclaw_hooks_url", ""),
        mcp_config.get("openclaw_hooks_token", ""),
        mcp_config.get("openclaw_channel_url", ""),
        mcp_config.get("openclaw_agent_transport", "hooks"),
    )
    platform.api_server = api_server
    if api_config.get("enabled", False) and not api_server.start_background():
        error = api_server.last_error or RuntimeError("unknown API startup error")
        QMessageBox.warning(None, "API service failed", str(error))

    # 创建系统托盘
    tray_config = platform.global_config.tray
    tray = None
    if tray_config.enabled:
        tray = SystemTrayIcon(platform)
        platform.system_tray = tray
        # 连接托盘信号
        tray.settings_requested.connect(lambda: _open_settings(platform))
        tray.create_instance_requested.connect(lambda: _open_settings(platform))
        tray.exit_requested.connect(lambda: _exit_platform(platform, app))

        # 若配置了 minimize_to_tray，关闭最后一个窗口也不退出
        if tray_config.minimize_to_tray:
            app.setQuitOnLastWindowClosed(False)

        # 启动时隐藏到托盘
        if start_hidden or platform.global_config.startup.start_hidden:
            for widget in platform.list_pet_widgets().values():
                widget.hide()

    sys.exit(app.exec())


# ----------------------------------------------------------------------
# 辅助函数
# ----------------------------------------------------------------------
def _open_settings(platform):
    """打开设置中心（单例模式，重复调用仅 raise 已有窗口）。"""
    global _settings_center_instance
    from .settings_center import SettingsCenter

    if _settings_center_instance is None:
        _settings_center_instance = SettingsCenter(platform)
    _settings_center_instance.show()
    _settings_center_instance.raise_()
    _settings_center_instance.activateWindow()


def _exit_platform(platform, app):
    """Persist and close the platform without deleting instance records."""
    try:
        platform.shutdown()
    except Exception as error:
        logger.exception("Platform shutdown failed")
        QMessageBox.critical(
            None,
            "Exit failed",
            f"Could not save desktop-pet state. The application will remain open.\n\n{error}",
        )
        return False
    app.quit()
    return True


if __name__ == "__main__":
    main()
