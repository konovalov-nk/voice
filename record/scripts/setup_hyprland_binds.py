#!/usr/bin/env python3
from pathlib import Path


def main() -> int:
    cfg_path = Path.home() / ".config/hypr/hyprland.conf"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    marker_start = "# recorderd binds start"
    marker_end = "# recorderd binds end"
    snippet = (
        "\n".join(
            [
                marker_start,
                "bind = SUPER, F9, exec, recorderctl start",
                "bind = SUPER, F10, exec, recorderctl stop",
                "bind = SUPER, F11, exec, recorderctl toggle",
                marker_end,
            ]
        )
        + "\n"
    )

    if not cfg_path.exists():
        cfg_path.write_text(snippet, encoding="utf-8")
        print(f"Created {cfg_path} with recorderd binds")
        return 0

    text = cfg_path.read_text(encoding="utf-8")
    if marker_start in text and marker_end in text:
        print("Hyprland binds already present")
        return 0

    if not text.endswith("\n"):
        text += "\n"
    text += "\n" + snippet
    cfg_path.write_text(text, encoding="utf-8")
    print(f"Appended recorderd binds to {cfg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
