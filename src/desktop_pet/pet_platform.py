"""Top-level lifecycle and persistence owner for all desktop-pet instances."""
from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Callable

from .config_manager import GlobalConfigManager
from .instances_store import InstancesStore
from .pet_instance import (
    InstanceConflictError,
    InstanceNotFoundError,
    PackageNotFoundError,
    PetInstanceConfig,
    apply_instance_patch,
    generate_pet_id,
    validate_instance_config,
)
from .pet_loader import PetLoader, PetPackage

logger = logging.getLogger(__name__)


class PlatformLifecycleError(RuntimeError):
    pass


class PetPlatform:
    def __init__(self, config_dir: Path | None = None, widget_factory: Callable[[str, PetInstanceConfig, PetPackage], object] | None = None) -> None:
        from .utils import get_config_path
        self.config_dir = Path(config_dir or get_config_path())
        self.global_config = GlobalConfigManager(config_dir=self.config_dir)
        self.pet_loader = PetLoader()
        self.instances_store = InstancesStore(config_dir=self.config_dir)
        self.pet_packages: dict[str, PetPackage] = {}
        self._widgets: dict[str, object] = {}
        self._widget_factory = widget_factory
        self.api_server = None
        self.system_tray = None
        self.screen_manager = None
        self._load_pet_packages()

    def start(self) -> None:
        if self.screen_manager is None:
            self._init_shared_screen_manager()
        self._migrate_legacy_if_needed()

        configs = self.instances_store.load_instances_for_restore()
        candidates: list[tuple[str, object | None]] = []
        try:
            for config in configs:
                package = self._get_or_load_package(config.package)
                if package is None:
                    raise PackageNotFoundError(
                        f"pet package not found while restoring {config.pet_id}: {config.package}"
                    )
                validate_instance_config(
                    config, package, screen_count=self._screen_count()
                )
                candidates.append(
                    (config.pet_id, self._build_widget(config, package))
                )
            if configs:
                self.instances_store.save_all(configs)
        except Exception:
            for _, widget in candidates:
                self._close_widget(widget)
            raise

        activated: list[tuple[str, object | None]] = []
        try:
            for pet_id, widget in candidates:
                self._activate_widget(pet_id, widget, show=True)
                activated.append((pet_id, widget))
        except Exception:
            for pet_id, widget in activated:
                self._unregister_widget(pet_id)
                self._widgets.pop(pet_id, None)
                self._close_widget(widget)
            for pet_id, widget in candidates[len(activated):]:
                self._widgets.pop(pet_id, None)
                self._close_widget(widget)
            raise

    def shutdown(self) -> None:
        configs = self.instances_store.list_instances()
        by_id = {item.pet_id: item for item in configs}
        for pet_id, widget in self._widgets.items():
            get_config = getattr(widget, "get_config", None)
            if callable(get_config):
                current = get_config()
                if isinstance(current, PetInstanceConfig):
                    by_id[pet_id] = current.clone()
            config = by_id.get(pet_id)
            if config is None:
                continue
            x = getattr(widget, "x", None)
            y = getattr(widget, "y", None)
            if callable(x) and callable(y):
                px, py = x(), y()
                if type(px) is int and type(py) is int:
                    config.position = {"x": px, "y": py}
            if self.screen_manager is not None:
                info = self.screen_manager.screen_for_widget(widget)
                if info is not None:
                    config.screen_index = info.index
        self.instances_store.save_all([by_id[item.pet_id] for item in configs])
        if self.api_server is not None and not self.api_server.stop_background():
            detail = self.api_server.last_error or "unknown API shutdown error"
            raise PlatformLifecycleError(f"failed to stop API server: {detail}")
        if self.system_tray is not None:
            hide = getattr(self.system_tray, "hide", None)
            if callable(hide): hide()
        for pet_id, widget in list(self._widgets.items()):
            self._unregister_widget(pet_id)
            self._close_widget(widget)
        self._widgets.clear()

    def _init_shared_screen_manager(self) -> None:
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None: return
            from .screen_manager import ScreenManager
            self.screen_manager = ScreenManager(app)
        except Exception as exc:
            logger.warning("Failed to initialize ScreenManager: %s", exc)

    def create_instance(self, package_name: str, position: dict | None = None, config: PetInstanceConfig | dict | None = None) -> str:
        package = self._get_or_load_package(package_name)
        if package is None:
            raise PackageNotFoundError(f"pet package not found: {package_name}")
        if isinstance(config, PetInstanceConfig):
            candidate = copy.deepcopy(config)
            candidate.package = package.name
            if not candidate.pet_id:
                candidate.pet_id = generate_pet_id(package.name)
            if position is not None:
                candidate.position = copy.deepcopy(position)
            validate_instance_config(
                candidate, package, screen_count=self._screen_count()
            )
        else:
            candidate = PetInstanceConfig.from_package_defaults(package)
            patch = copy.deepcopy(config or {})
            if not isinstance(patch, dict):
                from .pet_instance import InstanceConfigError
                raise InstanceConfigError("instance config must be an object")
            patch.pop("package", None)
            if position is not None:
                patch["position"] = copy.deepcopy(position)
            candidate = apply_instance_patch(
                candidate, patch, package, screen_count=self._screen_count()
            )
        if not candidate.pet_id:
            candidate.pet_id = generate_pet_id(package.name)
        existing = self.instances_store.list_instances()
        if any(item.pet_id == candidate.pet_id for item in existing):
            raise InstanceConflictError(f"instance already exists: {candidate.pet_id}")
        candidate.primary = bool(candidate.primary or not existing)
        validate_instance_config(candidate, package, screen_count=self._screen_count())
        widget = self._build_widget(candidate, package)
        try:
            self.instances_store.save_all(existing + [candidate])
        except Exception:
            self._close_widget(widget)
            raise
        try:
            self._activate_widget(candidate.pet_id, widget, show=True)
        except Exception:
            self._widgets.pop(candidate.pet_id, None)
            self._unregister_widget(candidate.pet_id)
            self._close_widget(widget)
            try:
                self.instances_store.save_all(existing)
            except Exception as rollback_error:
                raise PlatformLifecycleError(
                    f"failed to roll back instance creation: {rollback_error}"
                ) from rollback_error
            raise
        self._refresh_system_tray()
        return candidate.pet_id

    def destroy_instance(self, pet_id: str) -> bool:
        config = self.instances_store.get_instance(pet_id)
        widget = self._widgets.get(pet_id)
        if config is None and widget is None:
            return False
        if config is not None:
            self.instances_store.remove_instance(pet_id)
        widget = self._widgets.pop(pet_id, None)
        self._unregister_widget(pet_id)
        if widget is not None: self._close_widget(widget)
        self._refresh_system_tray()
        return config is not None

    def get_instance_config(self, pet_id: str) -> PetInstanceConfig | None:
        return self.instances_store.get_instance(pet_id)

    def list_instances(self) -> list[PetInstanceConfig]:
        return self.instances_store.list_instances()

    def get_primary_instance(self) -> PetInstanceConfig | None:
        return self.instances_store.get_primary_instance()

    def get_pet_widget(self, pet_id: str) -> object | None:
        return self._widgets.get(pet_id)

    def list_pet_widgets(self) -> dict[str, object]:
        return dict(self._widgets)

    def update_instance_config(self, pet_id: str, updates: dict) -> PetInstanceConfig:
        current = self.instances_store.get_instance(pet_id)
        if current is None:
            raise InstanceNotFoundError(f"pet instance not found: {pet_id}")
        target_name = updates.get("package", current.package) if isinstance(updates, dict) else current.package
        package = self._get_or_load_package(target_name)
        if package is None:
            raise PackageNotFoundError(f"pet package not found: {target_name}")
        if target_name != current.package:
            return self._switch_instance_package(current, package, updates)
        candidate = apply_instance_patch(current, updates, package, screen_count=self._screen_count())
        if current.primary and not candidate.primary:
            raise InstanceConflictError("the current primary instance cannot be demoted directly")
        all_configs = self.instances_store.list_instances()
        for index, item in enumerate(all_configs):
            if item.pet_id == pet_id: all_configs[index] = candidate
            elif candidate.primary: item.primary = False
        widget = self._widgets.get(pet_id)
        applied = False
        try:
            if widget is not None:
                callback = getattr(widget, "on_config_updated", None)
                if callable(callback):
                    callback(candidate.clone())
                    applied = True
                    if self.screen_manager is not None:
                        info = self.screen_manager.screen_for_widget(widget)
                        if info is not None:
                            candidate.screen_index = info.index
                            candidate.position = {"x": int(widget.x()), "y": int(widget.y())}
                            for index, item in enumerate(all_configs):
                                if item.pet_id == pet_id:
                                    all_configs[index] = candidate
                                    break
            self.instances_store.save_all(all_configs)
        except Exception:
            if applied:
                try: callback(current.clone())
                except Exception: logger.exception("Failed to roll back widget %s", pet_id)
            raise
        self._refresh_system_tray()
        return self.instances_store.get_instance(pet_id) or candidate

    def _switch_instance_package(self, current: PetInstanceConfig, package: PetPackage, updates: dict) -> PetInstanceConfig:
        allowed = {"package", "primary", "position", "screen_index", "size", "rest_reminder", "movement", "behavior", "motion_mode"}
        unknown = set(updates) - allowed
        if unknown:
            from .pet_instance import InstanceConfigError
            raise InstanceConfigError(f"package switch cannot update: {', '.join(sorted(unknown))}")
        candidate = PetInstanceConfig.from_package_defaults(package, pet_id=current.pet_id)
        for field in ("primary", "position", "screen_index", "size", "rest_reminder", "movement", "behavior", "motion_mode"):
            setattr(candidate, field, copy.deepcopy(getattr(current, field)))
        candidate.click_detection = self._package_click_defaults(package)
        patch = {key: value for key, value in updates.items() if key != "package"}
        candidate = apply_instance_patch(candidate, patch, package, screen_count=self._screen_count())
        if current.primary and not candidate.primary:
            raise InstanceConflictError("the current primary instance cannot be demoted directly")
        new_widget = self._build_widget(candidate, package)
        all_configs = self.instances_store.list_instances()
        for index, item in enumerate(all_configs):
            if item.pet_id == current.pet_id: all_configs[index] = candidate
            elif candidate.primary: item.primary = False
        try:
            self.instances_store.save_all(all_configs)
        except Exception:
            self._close_widget(new_widget)
            raise
        old_widget = self._widgets.get(current.pet_id)
        self._unregister_widget(current.pet_id)
        self._activate_widget(current.pet_id, new_widget, show=True)
        if old_widget is not None: self._close_widget(old_widget)
        self._refresh_system_tray()
        return self.instances_store.get_instance(current.pet_id) or candidate

    def persist_instance_position(self, pet_id: str, x: int, y: int) -> None:
        self.update_instance_config(pet_id, {"position": {"x": int(x), "y": int(y)}})

    def persist_instance_screen(self, pet_id: str, screen_index: int) -> None:
        self.update_instance_config(pet_id, {"screen_index": int(screen_index)})

    def persist_instance_config(self, pet_id: str) -> None:
        widget = self._widgets.get(pet_id)
        if widget is None:
            return
        get_config = getattr(widget, "get_config", None)
        if not callable(get_config):
            return
        config = get_config()
        if not isinstance(config, PetInstanceConfig):
            return
        self.instances_store.replace_instance(config)

    def _screen_count(self) -> int | None:
        if self.screen_manager is None: return None
        try: return len(self.screen_manager.all_screens())
        except Exception: return None

    def _load_pet_packages(self) -> None:
        try:
            for package in self.pet_loader.scan_pets(): self.pet_packages[package.name] = package
        except Exception:
            logger.exception("Failed to scan pet packages")

    def _get_or_load_package(self, package_name: str) -> PetPackage | None:
        package = self.pet_packages.get(package_name)
        if package is None:
            package = self.pet_loader.load_pet(package_name)
            if isinstance(package, PetPackage): self.pet_packages[package.name] = package
            else: package = None
        return package

    def _migrate_legacy_if_needed(self) -> None:
        if self.instances_store.exists:
            return
        path = self.config_dir / "user_config.json"
        if not path.exists(): return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to read legacy config: %s", exc)
            return
        package_name = data.get("app", {}).get("current_pet") if isinstance(data.get("app"), dict) else None
        if not isinstance(package_name, str) or not package_name: return
        package = self._get_or_load_package(package_name)
        if package is None: return
        config = PetInstanceConfig.from_package_defaults(package)
        config.primary = True
        if isinstance(data.get("pet"), dict) and "size" in data["pet"]: config.size = data["pet"]["size"]
        for section in ("rest_reminder", "movement", "behavior", "motion_mode", "click_detection"):
            if isinstance(data.get(section), dict): setattr(config, section, {**getattr(config, section), **copy.deepcopy(data[section])})
        display = data.get("display")
        if isinstance(display, dict) and type(display.get("last_screen_index")) is int: config.screen_index = display["last_screen_index"]
        legacy_actions = data.get("actions")
        if isinstance(legacy_actions, dict):
            allowed = {"enabled", "weight", "type", "config"}
            for name, raw in legacy_actions.items():
                if name in config.actions and isinstance(raw, dict):
                    config.actions[name].update({key: copy.deepcopy(value) for key, value in raw.items() if key in allowed})
        try:
            validate_instance_config(config, package, screen_count=self._screen_count())
        except Exception as exc:
            logger.warning("Legacy config required normalization: %s", exc)
            if config.screen_index is not None and self._screen_count() is not None and config.screen_index >= self._screen_count(): config.screen_index = None
            validate_instance_config(config, package, screen_count=self._screen_count())
        self.instances_store.save_all([config])

    def _package_click_defaults(self, package: PetPackage) -> dict:
        path = package.config_dir / "click_zones.json"
        if not path.exists(): return {"enabled": False, "zones": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data.get("click_detection"), dict): return copy.deepcopy(data["click_detection"])
            if isinstance(data.get("zones"), list): return {"enabled": bool(data.get("enabled", True)), "zones": copy.deepcopy(data["zones"])}
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to load click zones for package %s", package.name)
        return {"enabled": False, "zones": []}

    def _build_widget(self, config: PetInstanceConfig, package: PetPackage) -> object | None:
        if self._widget_factory is None: return None
        widget = self._widget_factory(config.pet_id, config.clone(), package)
        hide = getattr(widget, "hide", None)
        if callable(hide): hide()
        return widget

    def _activate_widget(self, pet_id: str, widget: object | None, *, show: bool) -> None:
        if widget is None: return
        self._widgets[pet_id] = widget
        if self.screen_manager is not None:
            register = getattr(self.screen_manager, "register_pet", None)
            if callable(register): register(pet_id, widget)
        if show:
            method = getattr(widget, "show", None)
            if callable(method): method()

    def _unregister_widget(self, pet_id: str) -> None:
        if self.screen_manager is not None:
            unregister = getattr(self.screen_manager, "unregister_pet", None)
            if callable(unregister): unregister(pet_id)

    def _close_widget(self, widget: object | None) -> None:
        if widget is None: return
        close = getattr(widget, "close", None)
        if callable(close): close()
        else:
            delete = getattr(widget, "deleteLater", None)
            if callable(delete): delete()

    def _refresh_system_tray(self) -> None:
        if self.system_tray is None: return
        refresh = getattr(self.system_tray, "refresh_menu", None)
        if callable(refresh): refresh()
