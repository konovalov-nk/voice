# recorderd

Minimal PipeWire recorder daemon that writes two parallel WAV streams:

- `mic`: current default microphone (resolved at runtime)
- `sys`: monitor node (what you hear from output)

## What Is Implemented

- `recorderd` user daemon with control commands over unix socket: `start`, `stop`, `toggle`, `status`, `ping`, `waybar`
- Parallel recording with two `pw-record` processes per session (`mic.wav` + `sys.wav`)
- Session file naming by timestamp + random hash: `YYYY-MM-DD-HH-MM-SS-<4hex>.wav`
- Runtime PID tracking in `$XDG_RUNTIME_DIR/recorderd`
- Automatic default mic resolution on every `start` (no hardcoded mic in service unit)
- `system_target` support for monitor sources, including virtual sinks
- Reliable sink-capture mode for system recording via `pw-record -P '{ stream.capture.sink=true }'`
- `recorderctl` CLI to control daemon from shell/hotkeys
- `recorder-transcribe` (and `recorderctl transcribe`) to generate .srt subtitles next to recordings using faster-whisper (config-driven defaults + optional auto after stop)
- `recorderd.service` for systemd user session lifecycle
- `Makefile` for setup, target config, Hyprland binds, service restart, and transcription
- Waybar integration via `recorderctl waybar` (returns JSON with text/class/tooltip)

## Files

- `recorderd` - daemon (`start|stop|toggle|status|ping|waybar` over unix socket)
- `recorderctl` - CLI client for daemon control
- `recorder-transcribe` - STT tool: writes `.srt` next to `.wav` (use via `recorderctl transcribe` or `make transcribe`)
- `recorderd.service` - systemd user unit
- `config.toml.example` - config template
- `hyprland.conf.example` - keybind examples

## Install

```bash
install -Dm755 recorderd ~/.local/bin/recorderd
install -Dm755 recorderctl ~/.local/bin/recorderctl
install -Dm755 recorder-transcribe ~/.local/bin/recorder-transcribe
install -Dm644 recorderd.service ~/.config/systemd/user/recorderd.service
install -Dm644 config.toml.example ~/.config/recorderd/config.toml
systemctl --user daemon-reload
systemctl --user enable --now recorderd.service
```

Or run all setup steps with Make:

```bash
make setup
```

Targets:

- `make install` - install binaries/unit, create config only if missing, start service
- `make configure-target` - auto-fill `system_target` from current default sink monitor
- `make setup-hyprland-binds` - append recorder hotkeys to `~/.config/hypr/hyprland.conf`
- `make restart-service` - restart `recorderd` after config changes
- `make transcribe` - transcribe the latest session using settings from config (stt_* keys). Respects `stt_transcribe_mic` / `stt_transcribe_sys`.
- `make transcribe-both` - force transcribe both mic and sys for the last session
- `make transcribe-select` - select one session interactively, transcribe both tracks and merge them
- `make transcribe-all` - detect all paired sessions, create missing mic/sys subtitles and merged text files
- `make transcribe-all-force` - regenerate all subtitles and merged text files from scratch

## How It Works

1. `recorderctl start` sends command to `$XDG_RUNTIME_DIR/recorderd/control.sock`.
2. `recorderd` resolves:
   - `mic_target`: from config (`mic_target`) or current default source at runtime.
   - `sys_target`: from config (`system_target`), expected as monitor source name.
3. Daemon creates output paths:
   - `~/.local/share/recorderd/mic/<timestamp>.wav`
   - `~/.local/share/recorderd/sys/<timestamp>.wav`
4. Daemon launches two `pw-record` processes:
   - Mic: regular source capture with `--target <mic_target>`.
   - System: if target ends with `.monitor`, daemon enables sink-capture mode
     (`-P '{ stream.capture.sink=true }'`) and targets base sink name.
5. Daemon writes runtime metadata:
   - `recording-mic.pid`, `recording-sys.pid`
   - state snapshot: `~/.local/state/recorderd/last.json`
6. `recorderctl stop` terminates both `pw-record` processes and cleans PID files.

## Configure system monitor target

Set `system_target` in `~/.config/recorderd/config.toml` to your monitor node name.

Helpful commands:

```bash
wpctl status
wpctl inspect <ID>
pactl list short sources
pactl list short sinks
```

Look for a node name ending with `.monitor`.

Example for a virtual sink monitor:

```toml
system_target = "umc404hd_aux01.monitor"
```

Example for a hardware sink monitor:

```toml
system_target = "alsa_output.usb-BEHRINGER_UMC404HD_192k-00.pro-output-0.monitor"
```

## Usage

```bash
recorderctl start
recorderctl status
recorderctl stop
recorderctl transcribe     # or: make transcribe
```

This produces `.srt` next to the `.wav` using good defaults (see Transcription section below).

For Hyprland, add binds (or use `make setup-hyprland-binds`):

```ini
bind = SUPER, F9, exec, recorderctl start
bind = SUPER, F10, exec, recorderctl stop
bind = SUPER, F11, exec, recorderctl toggle
```

Output files:

- `~/.local/share/recorderd/mic/YYYY-MM-DD-HH-MM-SS-<hash>.wav`
- `~/.local/share/recorderd/sys/YYYY-MM-DD-HH-MM-SS-<hash>.wav`

Transcription adds:

- `.../mic/<same-timestamp>.srt` (and/or under `sys/`) — standard SRT with timestamps, generated by `recorder-transcribe` / `make transcribe` / `recorderctl transcribe`

The 4-hex-char random hash prevents filename collision if two recordings start in the same second.

## Transcription (STT)

After a recording you can generate subtitles (`.srt`) next to the `.wav` files using faster-whisper.

The `.srt` is placed in the **same directory** as the source audio:

- `~/.local/share/recorderd/mic/YYYY-MM-DD-HH-MM-SS-<hash>.srt`
- (optionally the same for `sys/`)

### One-command transcription (recommended defaults)

```bash
# after you stopped the recording
recorderctl stop
recorderctl transcribe
# or even shorter if you are in the repo / have it in PATH
recorder-transcribe
```

Or using make:

```bash
make transcribe
make transcribe-both
```

The actual defaults for model, language, device and **which tracks** are taken from `~/.config/recorderd/config.toml` (flat keys with `stt_` prefix, same style as the rest of the config):

```toml
stt_model = "medium"
stt_language = "ru"
stt_device = "cuda"
stt_transcribe_mic = true
stt_transcribe_sys = false     # set to true → bare commands (make transcribe / recorder-transcribe) will do both tracks by default
stt_mic_label = "MIC"          # speaker labels in merged interview text
stt_sys_label = "SYS"
stt_auto_after_stop = false
```

### Auto-transcription after stop

If you set `stt_auto_after_stop = true` in the config and restart the service:

```bash
recorderctl stop
# .srt(s) will be generated automatically in the background
```

The daemon will launch `recorder-transcribe <session>` (respecting the track settings from config) as a detached process after every successful stop.

To enable:

```toml
stt_auto_after_stop = true
```

Then:

```bash
make restart-service
```

You can still override everything with explicit flags (`--both`, `--model small`, `--force`, etc.).

### Process and merge all sessions

To select one session from a numbered list without typing its ID:

```bash
recorder-transcribe --select
# short form
recorder-transcribe -i
# or
make transcribe-select
```

Add `--force` to regenerate the selected session from scratch.

The batch command finds session IDs that have both `mic/*.wav` and `sys/*.wav`. It creates only missing `.srt` files and then writes a chronological `<session>-interview.txt` with timestamps and speaker labels:

```bash
recorder-transcribe --all
# or
recorderctl transcribe --all
# or
make transcribe-all
```

Repeated runs skip existing outputs. To recreate every SRT and merged text file:

```bash
recorder-transcribe --all --force
# or
make transcribe-all-force
```

For one session, use `--both --merge`. Labels can be configured with `stt_mic_label` / `stt_sys_label` or overridden with `--mic-label` / `--sys-label`.

### Other useful invocations

```bash
# force re-transcribe last session
recorder-transcribe --last --force

# transcribe both mic and system audio
recorder-transcribe --last --both

# use a different model or language
recorder-transcribe --last --model small --language auto
recorder-transcribe 2026-06-08-18-07-07-9faa --model medium --sys

# from recorderctl (forwards all args)
recorderctl transcribe --last --model medium --both
```

### Installation of the STT backend

The transcription tool requires `faster-whisper`:

```bash
python3 -m pip install --user --break-system-packages faster-whisper
```

The script will auto-handle CUDA library soname quirks (common when mixing recent torch + nvidia pip wheels) by creating the necessary compatibility symlinks under `~/.cache/recorderd/cu12-compat`.

### Notes

- Transcription is intentionally **not** done inside the daemon — it is a separate, potentially long-running GPU/CPU job.
- You can bind it to a hotkey in Hyprland after stop, or just run it from terminal / `make`.
- For very long sessions `small` or `medium` are practical; `large-v3` gives higher quality at higher cost.
- If the beginning of your recordings is mostly music, VAD (`--no-vad` to disable) helps a lot.

## Waybar indicator

Add a custom module to your waybar config:

```json
"custom/recorderd": {
    "exec": "recorderctl waybar",
    "interval": 1,
    "return-type": "json"
}
```

Style with CSS:

```css
#custom-recorderd {
    color: #a6e3a1;
}
#custom-recorderd.idle {
    color: #6c7086;
}
```

Runtime files:

- `$XDG_RUNTIME_DIR/recorderd/control.sock`
- `$XDG_RUNTIME_DIR/recorderd/recording-mic.pid`
- `$XDG_RUNTIME_DIR/recorderd/recording-sys.pid`

State file:

- `~/.local/state/recorderd/last.json`

## Troubleshooting

- If both files contain mic, verify `system_target` points to a monitor source (`*.monitor`), not to a plain input source.
- If monitor target exists but capture is wrong, restart daemon after config changes: `make restart-service`.
- Check active targets and states: `pactl list short sources`.
- Check daemon logs: `journalctl --user -u recorderd.service -n 100 --no-pager`.
