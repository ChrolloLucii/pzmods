# pz-mod-sync

CLI-инструмент для синхронизации модов Project Zomboid из Steam Workshop через **SteamCMD с авторизацией под вашим Steam-аккаунтом**.

## Что делает программа

- Загружает манифест модпака из локального JSON-файла или по HTTPS URL.
- Запускает скачивание/обновление Workshop-модов через SteamCMD (`+login <username>`).
- Устанавливает найденные моды (по `mod.info`) в локальную папку `Zomboid/mods`.
- Проверяет наличие обязательных `ModID` из манифеста.
- Пишет логи и выводит JSON-отчёт по синхронизации.

## Безопасность и ограничения

- Нет анонимной загрузки Workshop.
- Нет передачи или шаринга учётных данных.
- Пароль не перехватывается программой (его запрашивает сам SteamCMD).
- Нет обходов лицензий/доступа и пиратских сценариев.

## Требования

- Python 3.10+
- Установленный SteamCMD (отдельно)
- Steam-аккаунт с доступом к нужным Workshop-элементам

## Установка

```powershell
pip install -e .
```

Если не получается активировать venv из-за ExecutionPolicy, можно запускать напрямую через:

```powershell
.\.venv\Scripts\python.exe -m pz_mod_sync.cli <команда>
```

Для удобного запуска без длинного пути:

1) Из папки проекта через лаунчер:

```powershell
.\pzmods doctor
.\pzmods sync --manifest sample-manifest/pz-modpack.json --steamcmd "D:\steamcmd\steamcmd.exe" --steam-user LOGIN
```

2) Через исполняемый скрипт в venv:

```powershell
.\.venv\Scripts\pzmods.exe doctor
```

3) Чтобы запускать просто `pzmods` в текущей сессии PowerShell:

```powershell
$env:Path = "$PWD\.venv\Scripts;$env:Path"
pzmods doctor
```

## Команды

```text
pzmods sync --manifest <path_or_url> [--steamcmd <path>] [--steam-user <name>] [--pzdir <path>] [--cache <path>] [--install-mode copy|symlink] [--download-mode always|missing-only|none]
pzmods validate --manifest <path_or_url> [--pzdir <path>]
pzmods doctor [--steamcmd <path>] [--pzdir <path>]
pzmods print-paths
pzmods parse-collection --collection <url_or_id> [--out pz-modpack.generated.json] [--name "..."]
pzmods add-workshop-item --manifest <local_manifest.json> --item <workshop_url_or_id>
pzmods merge-collection --manifest <local_manifest.json> --collection <url_or_id>
pzmods generate-manifest [--out pz-modpack.from-installed.json] [--name "..."] [--pzdir <path>] [--cache <path>] [--app-id 108600] [--include-unmatched-modids]
```

## Формат манифеста

Пример: [sample-manifest/pz-modpack.json](sample-manifest/pz-modpack.json).

## Полезные сценарии

1. Сгенерировать манифест из коллекции Steam:

```powershell
pzmods parse-collection --collection "https://steamcommunity.com/workshop/filedetails?id=3652192243" --out sample-manifest/collection.json
```

2. Добавить один мод по ссылке в существующий манифест:

```powershell
pzmods add-workshop-item --manifest sample-manifest/collection.json --item "https://steamcommunity.com/sharedfiles/filedetails?id=3635591071"
```

2.1. Добавить целую коллекцию в существующий манифест (без дубликатов):

```powershell
pzmods merge-collection --manifest sample-manifest/collection.json --collection "https://steamcommunity.com/workshop/filedetails?id=3652192243"
```

3. Сгенерировать манифест на основе уже установленных локально модов:

```powershell
pzmods generate-manifest --out sample-manifest/from-installed.json
```

4. Засинковать моды:

```powershell
.\pzmods.cmd sync --manifest "sample-manifest\pz-modpack.json" --steamcmd "D:\steamcmd\steamcmd.exe" --steam-user ВАШ_ЛОГИН_STEAM
```

По умолчанию в `mods_to_enable` попадут только ModID, которые удалось сопоставить с Workshop item ID.
Если нужно добавить и локальные/несопоставленные моды, используйте флаг `--include-unmatched-modids`.

## Примечания

- По умолчанию используется режим установки `copy` (чтобы избежать проблем с правами на symlink в Windows).
- Режим `symlink` — опционально для продвинутых пользователей.
- Повторный запуск `sync` идемпотентен: неизменённые моды пропускаются.
- Для ускорения повторной синхронизации используйте `--download-mode missing-only` (SteamCMD запускается только для отсутствующих workshop item).
- `--download-mode none` полностью пропускает шаг SteamCMD и использует уже скачанный кэш.

## Частые пути (Windows)

- Папка пользователя PZ: `%UserProfile%\\Zomboid`
- Папка модов: `%UserProfile%\\Zomboid\\mods`
- Логи/конфиг: `%AppData%\\pz-mod-sync`

## Тесты

```powershell
python -m unittest discover -s tests -v
```
