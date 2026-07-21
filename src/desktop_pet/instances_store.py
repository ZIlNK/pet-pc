"""Atomic persistence for desktop-pet instance configuration."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .pet_instance import PetInstanceConfig, generate_pet_id
from .pet_loader import PetPackage
from .utils import get_config_path

class InstancesStoreError(RuntimeError):
    pass

class InstancesStore:
    def __init__(self, config_dir: Path | None = None):
        self.config_dir = Path(config_dir or get_config_path())
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.instances_path = self.config_dir / "instances.json"

    @property
    def exists(self) -> bool:
        return self.instances_path.exists()

    def _load_raw(self) -> list[dict[str, Any]]:
        if not self.instances_path.exists():
            return []
        try:
            with self.instances_path.open("r", encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            raise InstancesStoreError(f"failed to read {self.instances_path}: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("instances"), list):
            raise InstancesStoreError("instances.json must contain an 'instances' array")
        raw = data["instances"]
        if not all(isinstance(item, dict) for item in raw):
            raise InstancesStoreError("every instance record must be an object")
        return copy.deepcopy(raw)

    def _save_raw(self, raw_instances: list[dict[str, Any]]) -> None:
        data = {"instances": raw_instances}
        temp_path: Path | None = None
        try:
            fd, temp_name = tempfile.mkstemp(prefix=".instances-", suffix=".tmp", dir=self.config_dir)
            temp_path = Path(temp_name)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, self.instances_path)
        except OSError as exc:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise InstancesStoreError(f"failed to save {self.instances_path}: {exc}") from exc

    @staticmethod
    def _normalize_primary(instances: list[PetInstanceConfig]) -> bool:
        if not instances:
            return False
        primary_indexes = [index for index, item in enumerate(instances) if item.primary]
        keep = primary_indexes[0] if primary_indexes else 0
        changed = len(primary_indexes) != 1
        for index, item in enumerate(instances):
            expected = index == keep
            if item.primary != expected:
                item.primary = expected
                changed = True
        return changed

    def _load_configs(self, *, persist_normalization: bool = True) -> list[PetInstanceConfig]:
        try:
            configs = [PetInstanceConfig.from_dict(item) for item in self._load_raw()]
        except Exception as exc:
            if isinstance(exc, InstancesStoreError):
                raise
            raise InstancesStoreError(f"invalid instance configuration: {exc}") from exc
        ids = [item.pet_id for item in configs]
        if len(ids) != len(set(ids)):
            raise InstancesStoreError("instances.json contains duplicate pet_id values")
        changed = self._normalize_primary(configs)
        if changed and persist_normalization:
            self._save_raw([item.to_dict() for item in configs])
        return configs

    def list_instances(self) -> list[PetInstanceConfig]:
        return [item.clone() for item in self._load_configs()]

    def load_instances_for_restore(self) -> list[PetInstanceConfig]:
        """Load and normalize in memory without rewriting the source file yet."""
        return [
            item.clone()
            for item in self._load_configs(persist_normalization=False)
        ]

    def get_instance(self, pet_id: str) -> PetInstanceConfig | None:
        return next((item.clone() for item in self._load_configs() if item.pet_id == pet_id), None)

    def get_primary_instance(self) -> PetInstanceConfig | None:
        return next((item.clone() for item in self._load_configs() if item.primary), None)

    def add_instance(self, config: PetInstanceConfig) -> None:
        instances = self._load_configs()
        candidate = config.clone()
        replaced = False
        for index, item in enumerate(instances):
            if item.pet_id == candidate.pet_id:
                instances[index] = candidate
                replaced = True
                break
        if not replaced:
            instances.append(candidate)
        if candidate.primary:
            for item in instances:
                item.primary = item.pet_id == candidate.pet_id
        self._normalize_primary(instances)
        self._save_raw([item.to_dict() for item in instances])

    def update_instance(self, pet_id: str, updates: dict) -> PetInstanceConfig | None:
        if not isinstance(updates, dict):
            raise InstancesStoreError("instance updates must be an object")
        if "pet_id" in updates:
            raise InstancesStoreError("pet_id cannot be changed")
        instances = self._load_configs()
        for index, item in enumerate(instances):
            if item.pet_id != pet_id:
                continue
            merged = item.to_dict()
            for key, value in updates.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = {**merged[key], **copy.deepcopy(value)}
                else:
                    merged[key] = copy.deepcopy(value)
            updated = PetInstanceConfig.from_dict(merged)
            instances[index] = updated
            if updated.primary:
                for other in instances:
                    other.primary = other.pet_id == pet_id
            self._normalize_primary(instances)
            self._save_raw([entry.to_dict() for entry in instances])
            return next(entry.clone() for entry in instances if entry.pet_id == pet_id)
        return None

    def replace_instance(self, config: PetInstanceConfig) -> PetInstanceConfig:
        instances = self._load_configs()
        for index, item in enumerate(instances):
            if item.pet_id != config.pet_id:
                continue
            instances[index] = config.clone()
            if config.primary:
                for other in instances:
                    other.primary = other.pet_id == config.pet_id
            self._normalize_primary(instances)
            self._save_raw([entry.to_dict() for entry in instances])
            return next(entry.clone() for entry in instances if entry.pet_id == config.pet_id)
        raise InstancesStoreError(f"instance {config.pet_id} does not exist")

    def remove_instance(self, pet_id: str) -> bool:
        instances = self._load_configs()
        remaining = [item for item in instances if item.pet_id != pet_id]
        if len(remaining) == len(instances):
            return False
        self._normalize_primary(remaining)
        self._save_raw([item.to_dict() for item in remaining])
        return True

    def save_all(self, instances: list[PetInstanceConfig]) -> None:
        copies = [item.clone() for item in instances]
        ids = [item.pet_id for item in copies]
        if len(ids) != len(set(ids)):
            raise InstancesStoreError("cannot save duplicate pet_id values")
        self._normalize_primary(copies)
        self._save_raw([item.to_dict() for item in copies])
        for original, normalized in zip(instances, copies):
            original.primary = normalized.primary

    def ensure_initial_instance(self, pet_package: PetPackage | None = None, legacy_current_pet: str = "default") -> PetInstanceConfig | None:
        if self._load_configs():
            return None
        if pet_package is None:
            return None
        config = PetInstanceConfig.from_package_defaults(pet_package, pet_id=generate_pet_id(pet_package.name))
        config.primary = True
        self.save_all([config])
        return config.clone()
