#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess


def list_sources() -> dict[str, str]:
    proc = subprocess.run(
        ["pactl", "list", "short", "sources"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {}
    sources: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        name = parts[1].strip()
        state = parts[-1].strip()
        if name:
            sources[name] = state
    return sources


def pick_monitor_target(sources: dict[str, str]) -> str:
    for name, state in sources.items():
        if (
            name.endswith(".monitor")
            and name.startswith("alsa_output.")
            and state.upper() == "RUNNING"
        ):
            return name

    default_sink_proc = subprocess.run(
        ["pactl", "get-default-sink"], check=False, capture_output=True, text=True
    )
    if default_sink_proc.returncode == 0:
        default_sink = default_sink_proc.stdout.strip()
        if default_sink:
            candidate = f"{default_sink}.monitor"
            if candidate in sources:
                return candidate

    for name, state in sources.items():
        if name.endswith(".monitor") and state.upper() == "RUNNING":
            return name
    for name in sources.keys():
        if name.endswith(".monitor"):
            return name
    return ""


def main() -> int:
    cfg_path = Path.home() / ".config/recorderd/config.toml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    if not cfg_path.exists():
        example = Path("config.toml.example")
        cfg_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")

    text = cfg_path.read_text(encoding="utf-8")
    current = re.search(r'^system_target\s*=\s*"([^"]*)"\s*$', text, flags=re.M)
    current_target = current.group(1).strip() if current else ""
    sources = list_sources()
    preferred_target = pick_monitor_target(sources)

    if current_target and current_target in sources:
        print(f"system_target already set: {current_target}")
        return 0

    target = preferred_target
    if not target:
        raise SystemExit(
            "Cannot detect any monitor source. Check PipeWire/Pulse sources and try again."
        )

    if current:
        text = re.sub(
            r'^system_target\s*=\s*"[^"]*"\s*$',
            f'system_target = "{target}"',
            text,
            count=1,
            flags=re.M,
        )
    else:
        text = f'system_target = "{target}"\n' + text

    cfg_path.write_text(text, encoding="utf-8")
    print(f"Configured system_target: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
