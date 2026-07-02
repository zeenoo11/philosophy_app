"""유파 = 프리셋 레지스트리 (SPEC §2.1).

프리셋 파일(YAML) = 그 유파의 명세서. 결정론 토글(deterministic)과 해석
정책(interpretation)을 한 파일에 둬 드리프트를 막는다. 새 유파 추가는 코드
수정이 아니라 presets/<id>.yaml 추가로 끝나야 한다 (SPEC §0.4, §6).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from engine.pillars import DeterministicConfig

_PRESET_DIR = Path(__file__).resolve().parent.parent / "presets"


@dataclass(frozen=True)
class Preset:
    preset_id: str
    display_name: str
    lineage: str
    description: str
    deterministic: DeterministicConfig
    interpretation: dict

    @property
    def engine(self) -> str:
        """해석 엔진 종류: 'yongsin' (용신 정책형) | 'structure' (맹파 등 우회형)."""
        return self.interpretation.get("engine", "yongsin")


def _to_config(d: dict) -> DeterministicConfig:
    """YAML deterministic 블록 → DeterministicConfig (알 수 없는 키 무시)."""
    fields = DeterministicConfig.__dataclass_fields__
    kw = {k: v for k, v in (d or {}).items() if k in fields}
    return DeterministicConfig(**kw)


@lru_cache(maxsize=64)
def load_preset(preset_id: str) -> Preset:
    path = _PRESET_DIR / f"{preset_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"프리셋 없음: {preset_id} ({path})")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw.get("preset_id") != preset_id:
        raise ValueError(f"preset_id 불일치: 파일명={preset_id} 내용={raw.get('preset_id')}")
    return Preset(
        preset_id=preset_id,
        display_name=raw.get("display_name", preset_id),
        lineage=raw.get("lineage", ""),
        description=raw.get("description", ""),
        deterministic=_to_config(raw.get("deterministic", {})),
        interpretation=raw.get("interpretation", {}) or {},
    )


def list_presets() -> list[str]:
    """presets/ 디렉터리의 모든 프리셋 id."""
    return sorted(p.stem for p in _PRESET_DIR.glob("*.yaml"))
