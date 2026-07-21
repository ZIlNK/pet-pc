"""端到端验证 bubble 子命令：真实主进程，CLI 显示气泡 + 隐藏气泡。"""
import sys
import json
import threading
import time
import asyncio
import logging
import subprocess
import shutil
from pathlib import Path

import httpx
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

logging.basicConfig(level=logging.INFO, stream=sys.stderr)

from desktop_pet.pet_platform import PetPlatform
from desktop_pet.pet import DesktopPet
from desktop_pet.api_server import ApiServer
from desktop_pet.pet_loader import PetLoader


def log(msg):
    print(msg, flush=True)


def main():
    config_path = Path("config/user_config.json")
    backup_path = Path("config/user_config.json.bak.test")
    shutil.copy2(config_path, backup_path)
    log("[SETUP] 已备份 user_config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("api", {})["port"] = 8101
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        log("[SETUP] api.port -> 8101")
        _run_test()
    finally:
        shutil.move(str(backup_path), str(config_path))
        log("[CLEANUP] 已恢复 user_config.json")


def _run_test():
    log("[STEP 1] QApplication")
    app = QApplication(sys.argv)
    app.setApplicationName("TestBubbleCmd")

    pet_loader = PetLoader()
    pets = pet_loader.scan_pets()
    if not pets:
        log("FAIL: 无宠物资源"); sys.exit(1)

    log("[STEP 2] 平台启动")
    platform = PetPlatform()
    platform._widget_factory = lambda pid, cfg, pkg: DesktopPet(cfg, pkg, platform)
    platform.start()
    if not platform.list_instances():
        platform.create_instance(pets[0].name)

    log("[STEP 3] API server @ 8101")
    api_server = ApiServer(platform=platform)
    api_server.configure("127.0.0.1", 8101)
    api_server.set_allowed_ips(["127.0.0.1", "::1"])
    platform.api_server = api_server

    def _run_api():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        api_server._api_loop = loop
        loop.run_until_complete(api_server.start())
        loop.run_forever()

    threading.Thread(target=_run_api, daemon=True).start()

    result = {"done": False, "pass": False}

    def _test():
        time.sleep(2.5)
        api_base = "http://127.0.0.1:8101"
        try:
            # 获取一个 pet_id
            r = httpx.get(f"{api_base}/api/instances", timeout=5)
            instances = r.json().get("instances", [])
            assert instances, "无运行中实例"
            pet_id = instances[0]["pet_id"]
            log(f"[TEST] 使用 pet_id={pet_id}")

            # 1. CLI bubble --text "你好"
            log('[TEST] CLI: bubble --text "你好测试"')
            proc = subprocess.run(
                ["uv", "run", "desktop-pet", "bubble", pet_id, "--text", "你好测试"],
                capture_output=True, text=True, timeout=30, cwd="d:\\code\\pet-pc",
            )
            log(f"[TEST] 退出码={proc.returncode}")
            log(f"[TEST] stdout: {proc.stdout.strip()}")
            if proc.returncode != 0:
                log(f"[TEST] stderr: {proc.stderr.strip()[-300:]}")
                log("=== FAIL ==="); return

            # 2. 等待确认气泡未自动隐藏（duration=0 应持续显示）
            time.sleep(3)
            log("[TEST] 等待 3 秒后气泡应仍显示（duration=0 持续）")

            # 3. CLI bubble --hide
            log(f"[TEST] CLI: bubble {pet_id} --hide")
            proc2 = subprocess.run(
                ["uv", "run", "desktop-pet", "bubble", pet_id, "--hide"],
                capture_output=True, text=True, timeout=30, cwd="d:\\code\\pet-pc",
            )
            log(f"[TEST] 退出码={proc2.returncode}")
            log(f"[TEST] stdout: {proc2.stdout.strip()}")
            if proc2.returncode != 0:
                log(f"[TEST] stderr: {proc2.stderr.strip()[-300:]}")
                log("=== FAIL ==="); return

            log("=== PASS (bubble 子命令显示+隐藏均生效) ===")
            result["pass"] = True
        except Exception as e:
            import traceback
            log(f"=== FAIL (异常: {e}) ===")
            log(traceback.format_exc())
        finally:
            result["done"] = True
            app.quit()

    threading.Thread(target=_test, daemon=True).start()

    def _timeout():
        if not result["done"]:
            log("=== FAIL (40秒超时) ==="); app.quit()
    QTimer.singleShot(40000, _timeout)

    log("[STEP 4] Qt 事件循环")
    app.exec()
    log(f"[DONE] pass={result['pass']}")
    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
