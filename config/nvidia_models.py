"""
NVIDIA 模型菜单（从 models/llm_models.yaml 读取，延迟加载避免循环导入）。
"""
from typing import Dict, List, Tuple

_CACHE: Dict[str, object] = {}


def _load():
    if _CACHE:
        return
    from services.llm.registry import get_registry

    reg = get_registry()
    nvidia = reg.list_menu_models("nvidia")
    _CACHE["entries"] = [
        (spec.key, spec.id, spec.display_name, spec.button_label) for spec in nvidia
    ]
    _CACHE["models"] = {spec.key: (spec.id, spec.display_name) for spec in nvidia}
    _CACHE["default_id"] = reg.default_model_id
    _CACHE["buttons"] = [(spec.button_label, spec.menu_callback()) for spec in nvidia]


def __getattr__(name: str):
    _load()
    if name == "NVIDIA_MODEL_ENTRIES":
        return _CACHE["entries"]
    if name == "NVIDIA_MODELS":
        return _CACHE["models"]
    if name == "NVIDIA_DEFAULT_MODEL_ID":
        return _CACHE["default_id"]
    if name == "NVIDIA_MODEL_BUTTONS":
        return _CACHE["buttons"]
    raise AttributeError(name)
