# Разработка Patisson Game

Этот документ — карта кода для дальнейшего развития игры. Игра написана в
**процедурном стиле**: один файл `patisson.py`, глобальное состояние +
функции-обработчики. Движок — [Ursina](https://www.ursinaengine.org/).

## Запуск среды разработки

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows;  source .venv/bin/activate на *nix
pip install -r requirements.txt
# положить ресурсы рядом с patisson.py (см. ASSETS.md)
python patisson.py
```

## Архитектура

Ursina вызывает по имени две глобальные функции каждый кадр / на ввод:

- **`update()`** — главный игровой цикл (каждый кадр): свободная камера,
  анимация колодца, рост/здоровье растения, смена дня и ночи, обновление HUD.
- **`input(key)`** — обработка нажатий: меню, инвентарь, ЛКМ (рыбалка/колодец/
  посадка/сбор), взаимодействие (`E`).

Состояние игры хранится в **глобальных переменных** (флаги режимов и числовые
параметры), объявленных в начале файла, например: `menu_visible`, `game_paused`,
`shop_visible`, `fishing_active`, `well_active`, `plant_growth`, `plant_water`,
`plant_food`, `plant_health`, `player_coins`, `player_fish`, `time_of_day`,
`free_camera_active`, `tutorial_active`/`tutorial_step` и др. Функции, которые их
меняют, используют `global`.

## Основные системы и функции

| Система | Ключевые функции |
|---------|------------------|
| Звук/музыка | `play_sound`, `start_menu_music`/`next_menu_track`, `start_game_music`/`next_game_track`, `stop_all_music` |
| Меню/настройки | `toggle_menu`, `open_settings`/`close_settings`, `open_sound_settings`, `update_volumes`, `save_settings`/`load_settings`, `open_controls_info`/`update_controls_info_text` |
| Туториал | `start_tutorial`, `update_tutorial`, `advance_tutorial`, `end_tutorial` |
| Магазин | `open_shop`/`close_shop`, `buy_item`, `update_button_state`, `change_shop_page`, `update_shop_display`, `shop_items_list` |
| Растение | `plant_plant`, `water_plant`, `feed_plant`, `remove_plant`, рост в `update()` |
| Сбор урожая | `start_harvest`, `create_harvest_button`, `harvest_button_clicked`, `finish_harvest` |
| Рыбалка | `start_fishing`, `create_fishing_button`, `fishing_button_clicked`, `finish_fishing`, `sell_fish` |
| Колодец | `start_well_animation`, `finish_well_animation`, `refill_water` (+ логика вращения в `update()`) |
| Инвентарь | `change_item`, `update_inventory_ui`, `update_seedling_icon`/`update_watering_can_icon`/`update_fishing_rod_icon` |
| День/ночь | `switch_time` (+ `time_of_day` в `update()`) |
| Консоль читов | `toggle_dev_panel`, `validate_cheat`, `apply_cheat` |
| Прочее | `check_map_boundaries`, `toggle_ui`, `toggle_elements`, `reset_game`, `start_game`, `exit_to_main_menu` |

## Ресурсы

Имена файлов ресурсов на русском (`Патиссон.glb`, `Колодец.glb`, `Лейка.png`…),
грузятся по относительному пути. Список — в [`ASSETS.md`](../ASSETS.md).

## Известные моменты / задел на будущее

Идеи для развития (issues приветствуются):

- [ ] Вынести глобальное состояние в класс/структуру `GameState` — упростит
      сохранения и тестирование.
- [ ] Разбить `patisson.py` на модули (ферма, рыбалка, магазин, UI, аудио).
- [ ] Сохранение прогресса игры (сейчас сохраняются только настройки звука).
- [ ] Баланс роста/здоровья растения вынести в конфиг.
- [ ] Локализация (сейчас тексты захардкожены на русском).
- [ ] Убрать отладочные `print(...)` из горячего пути (`update()`/`input()`).
- [ ] Достижения (кнопка есть, логика-заглушка `lambda: None`).

## Стиль

Менять `main` — это правка оригинального авторского кода Богдана. Крупные
изменения лучше обсуждать в issues и вести в отдельных ветках/PR, сохраняя
авторство.
