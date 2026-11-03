я короче вот шо хочу

сделать небольшой сервис который будет

- запускаться от пользователя когда
[Unit]
After=pipewire.service pipewire-pulse.service wireplumber.service
Wants=pipewire.service pipewire-pulse.service wireplumber.service
PartOf=pipewire.service wireplumber.service pipewire-pulse.service

[Service]
Type=simple
Environment=RECORDER_MIC_TARGET=(посмотри какой текущий сейчас по умолчанию)
Environment=RECORDER_SYS_TARGET=(UMC404HD_AUX0_1 monitor нода)
ExecStart=/home/br11k/.local/bin/recorderd
Restart=always
RestartSec=2

- далее он должен слушать сигналы-ивенты, например я через хоткей в hyprland делаю триггер (record/stop хоткеи) -> должны запускаться или останавливаться процессы по записи
- как только начинается запись: (1) создаётся папки/файлы ~/.local/share/state/mic + sys (2 папки)/{YYYY-MM-DD-HH-MM-SS}.wav  + recording-mic.pid файл где пишем pid процесса который записывает мик + recording-sys.pid (2) туда начинаем стримить/записывать звук микра / системы
- как только запись закончилась, останавливаем процессы, обновляем .pid файлы

