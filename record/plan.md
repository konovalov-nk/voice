Да — **готовые куски есть**, но именно твоего workflow “user service + hotkey trigger + две параллельные записи + pid/state/files” я бы не искал как готовый продукт. Самый нормальный путь тут: **свой тонкий orchestrator**, а сам захват звука отдать `pw-record` / `pw-cat`. `pw-record` — это штатный PipeWire CLI для записи в файл; он умеет писать WAV по расширению файла, выбирать target и настраивать latency. В `--target` можно передать `object.serial` или `node.name` нужной ноды. ([docs.pipewire.org][1])

Самое важное: я **не могу посмотреть твой текущий default mic** с этой стороны. Но у тебя это можно узнать локально так:

```bash
wpctl status
wpctl inspect @DEFAULT_AUDIO_SOURCE@
pactl get-default-source
```

`wpctl` умеет special IDs вроде `@DEFAULT_AUDIO_SOURCE@` и `@DEFAULT_AUDIO_SINK@`, а `pactl get-default-source` возвращает текущий default source. `wpctl status` показывает object IDs, а `wpctl inspect` даёт свойства объекта. ([Arch Linux Manpages][2])

Я бы тебе советовал **не хардкодить current default mic в `Environment=` у systemd unit**. Лучше пусть `recorderd` при каждом `start-record` сам резолвит текущий default source и уже его использует. Потому что “default” — штука runtime, и `wpctl` прямо пишет, что special identifiers резолвятся во время выполнения. ([Arch Linux Manpages][2])

По архитектуре я бы сделал так:

1. `recorderd` — маленький **user service**, который просто сидит и ждёт команду `start/stop/toggle`.
2. Hotkey в Hyprland дёргает не аудио-команды напрямую, а `recorderctl toggle`.
3. `recorderctl` шлёт команду в daemon через **Unix socket** в `$XDG_RUNTIME_DIR/recorderd.sock`.
4. Daemon на `start` создаёт timestamp, папки, запускает **два `pw-record` subprocess**:

   * mic → current default source
   * sys → твой monitor node
5. На `stop` daemon шлёт SIGTERM обоим `pw-record`, ждёт завершения, чистит runtime pid files.

Это проще и чище, чем городить D-Bus с нуля или пытаться делать “always-running recording processes”. Для контроля можно ещё логировать в journald. А если очень хочется без сокета, можно вообще использовать `systemctl --user kill -s USR1 recorderd` / `USR2`, но сокет обычно приятнее. Для runtime-файлов и сокетов XDG рекомендует `$XDG_RUNTIME_DIR`; для данных — `$XDG_DATA_HOME` (по умолчанию `~/.local/share`), для state — `$XDG_STATE_HOME` (по умолчанию `~/.local/state`), для cache — `$XDG_CACHE_HOME` (по умолчанию `~/.cache`). ([specifications.freedesktop.org][3])

То есть пути я бы раскладывал так:

* конфиг: `~/.config/recorderd/config.toml`
* записи:

  * `~/.local/share/recorderd/mic/YYYY-MM-DD-HH-MM-SS.wav`
  * `~/.local/share/recorderd/sys/YYYY-MM-DD-HH-MM-SS.wav`
* state:

  * `~/.local/state/recorderd/history.db`
  * `~/.local/state/recorderd/last.json`
* runtime:

  * `$XDG_RUNTIME_DIR/recorderd/recording-mic.pid`
  * `$XDG_RUNTIME_DIR/recorderd/recording-sys.pid`
  * `$XDG_RUNTIME_DIR/recorderd/control.sock`

То, что ты написал как `~/.local/share/state/...`, я бы **не делал**: по XDG это два разных мира — data и state. Pid-файлы вообще лучше держать в runtime dir, а не в home. ([specifications.freedesktop.org][3])

Про cache: **скорее всего не нужен вообще**. Нужен только если у тебя потом появятся временные ресемплы, waveform previews, промежуточные chunk’и для ASR, временный FLAC/PCM и тому подобное. Для простого “записал mic + monitor в WAV” можно обойтись без `~/.cache/recorderd`. ([specifications.freedesktop.org][3])

Ещё один тонкий момент: для `sys` записи я бы таргетил **не numeric ID**, а **`node.name`** monitor-ноды. `pw-record` это поддерживает напрямую, и это обычно приятнее, чем завязываться на то, что ты увидел в одном конкретном `wpctl status`. Чтобы взять точное имя, сначала находишь ноду через `wpctl status`, потом смотришь её свойства через `wpctl inspect ID`. ([docs.pipewire.org][1])

И да, с monitor-нodedами есть ещё один нюанс в WirePlumber: default source/sink выбираются по `priority.session`. В документации отдельно предупреждают, что если задрать priority sink слишком высоко, monitor sink’а может внезапно стать default source. Для sink’ов советуют не лезть выше 1500 именно из-за этого. ([pipewire.pages.freedesktop.org][4])

Так что мой вердикт такой:

**Не ищи большой готовый app.**
**Не пиши свой low-level recorder.**
**Сделай свой маленький `recorderd`, который оркестрирует `pw-record`.**

Это как раз sweet spot: мало кода, всё прозрачно, PipeWire делает тяжёлую работу, а твоя логика — только lifecycle, paths, pid/state и hotkey control.

Если хочешь, я могу сразу накидать минимальный `recorderd` design: `config.toml`, systemd user unit, и скелет `recorderctl toggle` + `recorderd` state machine.

[1]: https://docs.pipewire.org/page_man_pw-cat_1.html "PipeWire: pw-cat"
[2]: https://man.archlinux.org/man/extra/wireplumber/wpctl.1.en "wpctl(1) — Arch manual pages"
[3]: https://specifications.freedesktop.org/basedir/latest/?utm_source=chatgpt.com "XDG Base Directory Specification"
[4]: https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/alsa.html "ALSA configuration — WirePlumber 0.5.14 documentation"
