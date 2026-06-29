import json
from pathlib import Path
from nonebot_plugin_localstore import get_plugin_data_dir

_session_models: dict[str, str] = {}
_models_file: Path | None = None

def _get_models_file() -> Path:
      """和 MemoryManager 一样，数据放在插件 data 目录下"""
      return get_plugin_data_dir() / "ai_chat" / "session_models.json"


def _load_session_models():
    """模块加载时调用，从文件恢复"""
    global _session_models
    _models_file = _get_models_file()
    if _models_file.exists():
        try:
            _session_models = json.loads(_models_file.read_text(encoding="utf-8"))
        except Exception:
            _session_models = {}


def _save_session_models():
    """每次切模型时调用，写入文件"""
    global _models_file
    if _models_file is None:
        _models_file = _get_models_file()
    
    _models_file.parent.mkdir(parents=True, exist_ok=True)
    _models_file.write_text(
        json.dumps(_session_models, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def get_session_model(session_id: str, default_model: str) -> str:
      """获取当前会话使用的模型名，没有覆盖则用默认值"""
      return _session_models.get(session_id, default_model)


def set_session_model(session_id: str, model: str):
    """设置会话的模型覆盖（/model 命令调用）"""
    _session_models[session_id] = model
    _save_session_models()