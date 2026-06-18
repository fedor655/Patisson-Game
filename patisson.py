from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import random
import math
import json

app = Ursina()

# === НАСТРОЙКИ И ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
window.fullscreen = False
window.exit_button.enabled = False

# Убираем прицел
Entity.default_shader = None
camera.ui.enabled = True

# Игровые переменные
menu_visible = game_paused = shop_visible = fishing_active = is_day = False
well_active = False
well_holding = False
well_sound_playing = False
ui_visible = True
main_menu_active = True  # Главное меню активно при запуске
settings_from_pause = False  # Отслеживаем, откуда открыты настройки
current_shop_page = inventory_index = fishing_clicks = plant_stage = time_of_day = 0
well_rotation_time = 0
well_total_rotations = 0
prev_mouse_angle = 0
items_per_page = 2
day_length = 20
tutorial_active = False  # Обучение отключено при запуске
tutorial_step = 0
free_camera_active = False
camera_speed = 10
camera_rotation_speed = 1000  # Увеличена чувствительность мыши
sound_volume = 1.0  # Громкость звуков
music_volume = 1.0  # Громкость музыки
master_volume = 1.0  # Общая громкость
harvest_active = False  # Добавляем переменную для мини-игры сбора патиссона
harvest_clicks = 0
harvest_clicks_needed = 10  # Количество кликов для сбора патиссона
game_ended = False  # Конец игры
end_text = None  # Надпись с поздравлением
end_menu_button = None  # Кнопка выхода в меню

# Параметры игрока и растения
player_water = player_food = max_water = 50
player_fish = 0
player_coins = 0
plant_health = plant_water = plant_food = 100
plant_growth = 0
fishing_clicks_needed = 10
has_seedling = has_golden_watering_can = has_enchanted_fishing_rod = False

# Переменные для читов
growth_speed_multiplier = 1.0
immortal_plant = False

# Управление (фиксированные клавиши)
key_bindings = {
    'forward': 'w',
    'backward': 's',
    'left': 'a',
    'right': 'd',
    'jump': 'space',
    'interact': 'e',
    'watering_can': '1',
    'fertilizer': '2',
    'fishing_rod': '3',
    'seedling': '4',
    'toggle_ui': 'f1',
    'dev_panel': 'f12',
    'menu': 'escape'
}

# Границы карты
MAP_SIZE = 25
SPAWN_POSITION = (0, 2, -3)
DEATH_Y = -10

# Объекты
plant = field = fishing_button = well_handle_3d = None
harvest_button = None
harvest_text = Text(parent=camera.ui, text="Патиссон вырос! Подойдите и сорвите его.", scale=2, position=(0, 0.4), origin=(0, 0), color=color.yellow, enabled=False, background=True)
end_text = None  # Надпись с поздравлением
end_menu_button = None  # Кнопка выхода в меню

# === СОЗДАНИЕ МИРА ===
sky_day = Sky(texture='День.jpg')
sky_night = Sky(texture='Ночь.jpg', visible=False)
ground = Entity(model='plane', scale=(50, 1, 50), texture='Трава.jpg', collider='box')
player = FirstPersonController(position=SPAWN_POSITION, collider='box')

# Убираем прицел у FirstPersonController
if hasattr(player, 'crosshair'):
    player.crosshair.enabled = False

# Здания и объекты
well = Entity(model='Колодец.glb', position=(8, 0.01, 8), scale=0.18, collider='box')
well_handle_3d = Entity(model='Рукоять.glb', position=(8.05, 1.8, 6.4), scale=0.5, rotation_y=90, collider='box')
shop = Entity(model='Магазин.glb', position=(-10, 0.1, -10), scale=0.01, collider='box')
shop_trigger = Entity(model='cube', position=(-10, 1, -10), scale=2, visible=False, collider='box')
pond = Entity(model='Водоём.glb', position=(-17, -0.05, 13), scale=0.2)
pond_collider = Entity(model='cylinder', position=(-17, 0, 13), scale=(8, 0.5, 7), visible=False, collider='box')
fish_seller = Entity(model='Прилавок.glb', position=(-12, -0.05, 19), scale=3.5, rotation_y=180, collider='box')
house = Entity(model='Дом.glb', position=(15, 0.01, -15), scale=0.8, rotation_y=90, collider='box')

# Поле и забор
field = Entity(model='cube', texture='Грядка.jpg', color=color.brown, scale=(1, 0.1, 1), position=(0, 0.05, 0), collider='box')

fence_positions = [
    *[(x, 0, 4, 110) for x in [-1.05, 4] if x != 0],
    *[(x, 0, -4, 110) for x in [-1.05, 4] if x != 0],
    *[(-4, 0, z, 20) for z in [-1.05, 4] if z != 0],
    *[(4, 0, z, 20) for z in [-1.05, 4] if z != 0]
]
for x, y, z, rot in fence_positions:
    Entity(model='Забор.glb', position=(x, y, z), scale=(0.7, 0.7, 0.7), rotation_y=rot, collider='box')

# === АУДИО ===
sounds = {
    'click': Audio('click.wav', autoplay=False, volume=1.0),
    'cash': Audio('Cash.wav', autoplay=False, volume=1.0),
    'nope': Audio('nope.wav', autoplay=False, volume=1.0),
    'death': Audio('aaaa.wav', autoplay=False),
    'hurt': Audio('hurt.wav', autoplay=False),
    'well': Audio('Колодец.wav', autoplay=False, volume=1.0),
    'fishing': Audio('Удочка.wav', autoplay=False, volume=1.0),
    'cast_rod': Audio('Закидывание.wav', autoplay=False, volume=1.0)
}

# Музыкальные треки
menu_tracks = ['Married Life.mp3', 'Gymnopedie No.mp3', 'Summer Harvest Theme.mp3']
game_tracks = ['Wynton Marsalis.mp3', 'Classic Easter.mp3', 'Bee Swarm.mp3', 'Spring.mp3', 'Rondo Alla Turca Mozart.mp3']

# Текущая музыка
current_menu_track = 0
current_game_track = 0
menu_music = None
game_music = None

def play_sound(name):
    try:
        sounds[name].volume = sound_volume * master_volume
        sounds[name].play()
    except:
        print(f"Не удалось воспроизвести звук {name}")

def start_menu_music():
    global menu_music, current_menu_track
    if menu_music:
        menu_music.stop()
    try:
        menu_music = Audio(menu_tracks[current_menu_track], autoplay=True, loop=False, volume=music_volume * master_volume)
        invoke(next_menu_track, delay=menu_music.length)
    except:
        invoke(next_menu_track, delay=180)  # Fallback на 3 минуты

def next_menu_track():
    global current_menu_track
    current_menu_track = (current_menu_track + 1) % len(menu_tracks)
    if main_menu_active:
        start_menu_music()

def start_game_music():
    global game_music, current_game_track
    if game_music:
        game_music.stop()
    try:
        game_music = Audio(game_tracks[current_game_track], autoplay=True, loop=False, volume=music_volume * master_volume)
        invoke(next_game_track, delay=game_music.length)
    except:
        invoke(next_game_track, delay=180)  # Fallback на 3 минуты

def next_game_track():
    global current_game_track
    current_game_track = (current_game_track + 1) % len(game_tracks)
    if not main_menu_active:
        start_game_music()

def stop_all_music():
    global menu_music, game_music
    if menu_music:
        menu_music.stop()
    if game_music:
        game_music.stop()

# === ОБУЧЕНИЕ ===
tutorial_panel = Entity(parent=camera.ui, model='quad', scale=(0.7, 0.5), color=color.black66, enabled=False, z=-0.1)
tutorial_text = Text(parent=camera.ui, text="Хотите пройти обучение?", scale=2, position=(0, 0.1), origin=(0, 0), color=color.white, enabled=False, background=False, z=-0.15)
tutorial_yes_button = Button(parent=tutorial_panel, text="Да", scale=(0.2, 0.1), position=(-0.15, -0.1), color=color.green, text_color=color.white, on_click=lambda: start_tutorial(), enabled=False)
tutorial_no_button = Button(parent=tutorial_panel, text="Нет", scale=(0.2, 0.1), position=(0.15, -0.1), color=color.red, text_color=color.white, on_click=lambda: end_tutorial(), enabled=False)

def start_tutorial():
    global tutorial_active, tutorial_step, game_paused
    tutorial_step = 1
    tutorial_active = True
    game_paused = False
    player.enabled = True
    mouse.locked = True
    mouse.visible = False
    toggle_elements([tutorial_panel, tutorial_yes_button, tutorial_no_button], False)
    toggle_ui(True)  # Показываем UI при начале обучения
    update_tutorial()

def end_tutorial():
    global tutorial_active, game_paused
    tutorial_active = False
    game_paused = False
    player.enabled = True
    mouse.locked = True
    mouse.visible = False
    toggle_elements([tutorial_panel, tutorial_text, tutorial_yes_button, tutorial_no_button], False)
    toggle_ui(True)  # Показываем UI после завершения обучения

def update_tutorial():
    global tutorial_step, game_paused, player_coins, player_fish, has_seedling
    tutorial_yes_button.enabled = False
    tutorial_no_button.enabled = False
    tutorial_texts = {
        1: "Нажмите W, A, S, D, чтобы двигаться,\nи используйте мышь для поворота камеры.",
        2: "Подойдите к магазину\nи нажмите E, чтобы открыть его.",
        3: "Нажмите Escape,\nчтобы закрыть магазин.",
        4: "Подойдите к водоёму, выберите удочку\n(клавиша 3) и нажмите ЛКМ, чтобы начать рыбалку.",
        5: "Кликните на красную кнопку,\nчтобы ловить рыбу. Поймайте 2 рыбы! (Осталось: 2)",
        6: "Кликните на красную кнопку,\nчтобы ловить рыбу. Поймайте 2 рыбы! (Осталось: 1)",
        7: "Подойдите к прилавку и нажмите E,\nчтобы продать рыбу за монеты.",
        8: "Вернитесь в магазин,\nкупите саженец.",
        9: "Выберите саженец (клавиша 4) и нажмите\nЛКМ на грядке в центре, чтобы посадить его.",
        10: "Выберите лейку (клавиша 1) и нажмите\nЛКМ на растении, чтобы полить его.",
        11: "Выберите удобрение (клавиша 2) и нажмите\nЛКМ на растении, чтобы удобрить его.",
        12: "Обучение завершено!\nВоду набирайте в колодце, удобрения — в магазине."
    }
    if tutorial_step in tutorial_texts:
        tutorial_text.text = tutorial_texts[tutorial_step]
        tutorial_text.scale = 1.2
        tutorial_text.position = (0, 0.35)
        tutorial_text.origin = (0, -0.5)
        tutorial_text.enabled = True
        tutorial_text.background = True
        tutorial_text.z = -0.05
    if tutorial_step == 5 or tutorial_step == 6:
        tutorial_text.text = tutorial_texts[tutorial_step].replace("(Осталось: 2)", f"(Осталось: {2 - player_fish})")
    if tutorial_step == 12:
        invoke(end_tutorial, delay=5)

# === ГЛАВНОЕ МЕНЮ ===
main_menu_bg = Entity(parent=camera.ui, model='quad', texture='Меню.mp4', scale=(1.8, 1), z=0.5, enabled=True)
main_menu_panel = Entity(parent=camera.ui, model='quad', scale=(1.8, 1), color=color.clear, enabled=True, z=-0.01)

play_button = Button(
    parent=main_menu_panel, 
    model='quad', 
    texture='Играть.png', 
    scale=(0.28, 0.17), 
    position=(-0.31, 0.19), 
    color=color.white, 
    z=-0.02, 
    enabled=True,
    on_click=lambda: start_game()
)

settings_button = Button(
    parent=main_menu_panel, 
    model='quad', 
    texture='Настройки.png', 
    scale=(0.28, 0.17), 
    position=(-0.31, 0.01), 
    color=color.white, 
    z=-0.02, 
    enabled=True,
    on_click=lambda: open_settings()
)

achievements_button = Button(
    parent=main_menu_panel, 
    model='quad', 
    texture='Достижения.png', 
    scale=(0.28, 0.17), 
    position=(-0.31, -0.17), 
    color=color.white, 
    z=-0.02, 
    enabled=True,
    on_click=lambda: None
)

exit_button_main = Button(
    parent=main_menu_panel, 
    model='quad', 
    texture='Выход.png', 
    scale=(0.28, 0.17), 
    position=(-0.31, -0.35), 
    color=color.white, 
    z=-0.02, 
    enabled=True,
    on_click=application.quit
)

def on_play_hover():
    play_button.texture = 'Играть2.png'

def on_play_unhover():
    play_button.texture = 'Играть.png'

def on_settings_hover():
    settings_button.texture = 'Настройки2.png'

def on_settings_unhover():
    settings_button.texture = 'Настройки.png'

def on_achievements_hover():
    achievements_button.texture = 'Достижения2.png'

def on_achievements_unhover():
    achievements_button.texture = 'Достижения.png'

def on_exit_hover():
    exit_button_main.texture = 'Выход2.png'

def on_exit_unhover():
    exit_button_main.texture = 'Выход.png'

play_button.on_mouse_enter = on_play_hover
play_button.on_mouse_exit = on_play_unhover
settings_button.on_mouse_enter = on_settings_hover
settings_button.on_mouse_exit = on_settings_unhover
achievements_button.on_mouse_enter = on_achievements_hover
achievements_button.on_mouse_exit = on_achievements_unhover
exit_button_main.on_mouse_enter = on_exit_hover
exit_button_main.on_mouse_exit = on_exit_unhover

# === ПАНЕЛЬ НАСТРОЙКИ ===
settings_panel = Entity(parent=camera.ui, model='quad', scale=(0.7, 0.5), color=color.black66, enabled=False, z=-0.1)
settings_title = Text(parent=settings_panel, text="Настройки", scale=2, position=(0, 0.3), origin=(0, 0), color=color.white, enabled=False)
sound_button = Button(
    parent=settings_panel, 
    model='quad', 
    texture='Звук.png', 
    scale=(0.3, 0.15), 
    position=(0, 0.15), 
    color=color.white, 
    z=-0.02, 
    enabled=False,
    on_click=lambda: open_sound_settings()
)
controls_info_button = Button(
    parent=settings_panel, 
    model='quad', 
    texture='Управление.png', 
    scale=(0.3, 0.15), 
    position=(0, -0.05), 
    color=color.white, 
    z=-0.02, 
    enabled=False,
    on_click=lambda: open_controls_info()
)
settings_back = Button(
    parent=settings_panel, 
    text="Назад", 
    scale=(0.2, 0.1), 
    position=(0, -0.25), 
    color=color.red, 
    text_color=color.white, 
    enabled=False,
    on_click=lambda: close_settings()
)

def on_sound_hover():
    sound_button.texture = 'Звук2.png'

def on_sound_unhover():
    sound_button.texture = 'Звук.png'

def on_controls_info_hover():
    controls_info_button.texture = 'Управление2.png'

def on_controls_info_unhover():
    controls_info_button.texture = 'Управление.png'

sound_button.on_mouse_enter = on_sound_hover
sound_button.on_mouse_exit = on_sound_unhover
controls_info_button.on_mouse_enter = on_controls_info_hover
controls_info_button.on_mouse_exit = on_controls_info_unhover

def open_settings():
    global game_paused, settings_from_pause
    settings_from_pause = False  # Открыто из главного меню
    toggle_elements([main_menu_bg, main_menu_panel, play_button, settings_button, achievements_button, exit_button_main], False)
    toggle_elements([settings_panel, settings_title, sound_button, controls_info_button, settings_back], True)
    game_paused = True
    mouse.locked = False
    mouse.visible = True
    player.enabled = False

def open_pause_settings():
    global game_paused, settings_from_pause
    settings_from_pause = True  # Открыто из меню паузы
    toggle_elements([menu_panel, continue_button, pause_settings_button, pause_achievements_button, exit_to_menu_button], False)
    toggle_elements([settings_panel, settings_title, sound_button, controls_info_button, settings_back], True)
    game_paused = True
    mouse.locked = False
    mouse.visible = True
    player.enabled = False

def close_settings():
    global game_paused, settings_from_pause
    toggle_elements([settings_panel, settings_title, sound_button, controls_info_button, settings_back], False)
    if settings_from_pause:
        # Возвращаемся в меню паузы
        toggle_elements([menu_panel, continue_button, pause_settings_button, pause_achievements_button, exit_to_menu_button], True)
        game_paused = True
        mouse.locked = False
        mouse.visible = True
        player.enabled = False
    else:
        # Возвращаемся в главное меню
        toggle_elements([main_menu_bg, main_menu_panel, play_button, settings_button, achievements_button, exit_button_main], True)
        game_paused = True
        mouse.locked = False
        mouse.visible = True
        player.enabled = False

# === ПАНЕЛЬ НАСТРОЕК ЗВУКА ===
sound_settings_panel = Entity(parent=camera.ui, model='quad', scale=(0.7, 0.5), color=color.black66, enabled=False, z=-0.1)
sound_settings_title = Text(parent=sound_settings_panel, text="Настройки звука", scale=2, position=(0, 0.2), origin=(0, 0), color=color.white, enabled=False)

# Определяем функцию change_volume перед созданием кнопок
def change_volume(volume_type, change):
    global sound_volume, music_volume, master_volume
    if volume_type == 'sound':
        sound_volume = max(0, min(1, sound_volume + change))
        sound_volume_text.text = f"Громкость звуков: {int(sound_volume * 100)}%"
    elif volume_type == 'music':
        music_volume = max(0, min(1, music_volume + change))
        music_volume_text.text = f"Громкость музыки: {int(music_volume * 100)}%"
    elif volume_type == 'master':
        master_volume = max(0, min(1, master_volume + change))
        master_volume_text.text = f"Общая громкость: {int(master_volume * 100)}%"
    update_volumes()

# Альтернатива ползункам: кнопки + и - для громкости
sound_volume_text = Text(parent=sound_settings_panel, text=f"Громкость звуков: {int(sound_volume * 100)}%", scale=1.5, position=(-0.2, 0.1), origin=(0, 0), color=color.white, enabled=False)
sound_volume_plus = Button(parent=sound_settings_panel, text="+", scale=(0.1, 0.1), position=(0.2, 0.1), color=color.green, text_color=color.white, enabled=False, on_click=Func(change_volume, 'sound', 0.1))
sound_volume_minus = Button(parent=sound_settings_panel, text="-", scale=(0.1, 0.1), position=(0.3, 0.1), color=color.red, text_color=color.white, enabled=False, on_click=Func(change_volume, 'sound', -0.1))

music_volume_text = Text(parent=sound_settings_panel, text=f"Громкость музыки: {int(music_volume * 100)}%", scale=1.5, position=(-0.2, 0), origin=(0, 0), color=color.white, enabled=False)
music_volume_plus = Button(parent=sound_settings_panel, text="+", scale=(0.1, 0.1), position=(0.2, 0), color=color.green, text_color=color.white, enabled=False, on_click=Func(change_volume, 'music', 0.1))
music_volume_minus = Button(parent=sound_settings_panel, text="-", scale=(0.1, 0.1), position=(0.3, 0), color=color.red, text_color=color.white, enabled=False, on_click=Func(change_volume, 'music', -0.1))

master_volume_text = Text(parent=sound_settings_panel, text=f"Общая громкость: {int(master_volume * 100)}%", scale=1.5, position=(-0.2, -0.1), origin=(0, 0), color=color.white, enabled=False)
master_volume_plus = Button(parent=sound_settings_panel, text="+", scale=(0.1, 0.1), position=(0.2, -0.1), color=color.green, text_color=color.white, enabled=False, on_click=Func(change_volume, 'master', 0.1))
master_volume_minus = Button(parent=sound_settings_panel, text="-", scale=(0.1, 0.1), position=(0.3, -0.1), color=color.red, text_color=color.white, enabled=False, on_click=Func(change_volume, 'master', -0.1))

sound_settings_back = Button(parent=sound_settings_panel, text="Назад", scale=(0.2, 0.1), position=(0, -0.25), color=color.red, text_color=color.white, on_click=lambda: close_sound_settings(), enabled=False)

def open_sound_settings():
    global game_paused
    toggle_elements([settings_panel, settings_title, sound_button, controls_info_button, settings_back], False)
    toggle_elements([sound_settings_panel, sound_settings_title, sound_volume_text, sound_volume_plus, sound_volume_minus, music_volume_text, music_volume_plus, music_volume_minus, master_volume_text, master_volume_plus, master_volume_minus, sound_settings_back], True)
    game_paused = True
    mouse.locked = False
    mouse.visible = True
    player.enabled = False

def close_sound_settings():
    global game_paused
    toggle_elements([sound_settings_panel, sound_settings_title, sound_volume_text, sound_volume_plus, sound_volume_minus, music_volume_text, music_volume_plus, music_volume_minus, master_volume_text, master_volume_plus, master_volume_minus, sound_settings_back], False)
    toggle_elements([settings_panel, settings_title, sound_button, controls_info_button, settings_back], True)
    game_paused = True
    mouse.locked = False
    mouse.visible = True
    player.enabled = False

def update_volumes():
    print(f"Обновление громкости: sound={sound_volume:.2f}, music={music_volume:.2f}, master={master_volume:.2f}")
    for sound in sounds.values():
        sound.volume = sound_volume * master_volume
    if menu_music:
        menu_music.volume = music_volume * master_volume
    if game_music:
        game_music.volume = music_volume * master_volume
    save_settings()  # Сохраняем настройки после изменения громкости

# === ПАНЕЛЬ ИНФОРМАЦИИ ОБ УПРАВЛЕНИИ ===
controls_info_panel = Entity(parent=camera.ui, model='quad', scale=(0.7, 0.7), color=color.black66, enabled=False, z=-0.1)
controls_info_title = Text(parent=controls_info_panel, text="Управление", scale=2, position=(0, 0.2), origin=(0, 0), color=color.white, enabled=False, z=-0.15)
controls_info_text = Text(parent=controls_info_panel, text="", scale=1.2, position=(0, 0.15), origin=(0, 0.5), color=color.white, enabled=False, background=True, z=-0.15)
controls_info_back = Button(parent=controls_info_panel, text="Назад", scale=(0.2, 0.1), position=(0, -0.3), color=color.red, text_color=color.white, on_click=lambda: close_controls_info(), enabled=False, z=-0.15)

def update_controls_info_text():
    controls_text = "\n".join(
        f"{label}: {key}"
        for label, action, key in [
            ('Движение вперёд', 'forward', key_bindings['forward'].upper()),
            ('Движение назад', 'backward', key_bindings['backward'].upper()),
            ('Движение влево', 'left', key_bindings['left'].upper()),
            ('Движение вправо', 'right', key_bindings['right'].upper()),
            ('Прыжок', 'jump', key_bindings['jump'].upper()),
            ('Взаимодействие', 'interact', key_bindings['interact'].upper()),
            ('Лейка (инвентарь)', 'watering_can', key_bindings['watering_can'].upper()),
            ('Удобрение (инвентарь)', 'fertilizer', key_bindings['fertilizer'].upper()),
            ('Удочка (инвентарь)', 'fishing_rod', key_bindings['fishing_rod'].upper()),
            ('Саженец (инвентарь)', 'seedling', key_bindings['seedling'].upper()),
            ('Переключить UI', 'toggle_ui', key_bindings['toggle_ui'].upper()),
            ('Меню паузы', 'menu', key_bindings['menu'].upper())
        ]
    )
    controls_info_text.text = controls_text

def open_controls_info():
    global game_paused
    update_controls_info_text()
    toggle_elements([settings_panel, settings_title, sound_button, controls_info_button, settings_back], False)
    toggle_elements([controls_info_panel, controls_info_title, controls_info_text, controls_info_back], True)
    game_paused = True
    mouse.locked = False
    mouse.visible = True
    player.enabled = False

def close_controls_info():
    global game_paused
    toggle_elements([controls_info_panel, controls_info_title, controls_info_text, controls_info_back], False)
    toggle_elements([settings_panel, settings_title, sound_button, controls_info_button, settings_back], True)
    game_paused = True
    mouse.locked = False
    mouse.visible = True
    player.enabled = False

# === ФУНКЦИЯ СОХРАНЕНИЯ И ЗАГРУЗКИ НАСТРОЕК ===
def save_settings():
    settings = {
        'sound_volume': sound_volume,
        'music_volume': music_volume,
        'master_volume': master_volume
    }
    try:
        with open('settings.json', 'w') as f:
            json.dump(settings, f)
        print("Настройки сохранены")
    except:
        print("Не удалось сохранить настройки")

def load_settings():
    global sound_volume, music_volume, master_volume
    try:
        with open('settings.json', 'r') as f:
            settings = json.load(f)
        sound_volume = settings.get('sound_volume', 1.0)
        music_volume = settings.get('music_volume', 1.0)
        master_volume = settings.get('master_volume', 1.0)
        print(f"Настройки загружены: sound={sound_volume:.2f}, music={music_volume:.2f}, master={master_volume:.2f}")
        update_volumes()  # Применяем загруженные настройки
    except:
        print("Не удалось загрузить настройки, используются значения по умолчанию")

# === МЕНЮ ПАУЗЫ ===
menu_panel = Entity(parent=camera.ui, model='quad', scale=(1.8, 1), color=color.black66, enabled=False, z=-0.1)

continue_button = Button(
    parent=menu_panel, 
    model='quad', 
    texture='ПРигру.png', 
    scale=(0.4, 0.1), 
    position=(0, 0.3), 
    color=color.white, 
    z=-0.02, 
    enabled=False,
    on_click=lambda: toggle_menu()
)

pause_settings_button = Button(
    parent=menu_panel, 
    model='quad', 
    texture='Настройки3.png', 
    scale=(0.4, 0.1), 
    position=(0, 0.1), 
    color=color.white, 
    z=-0.02, 
    enabled=False,
    on_click=lambda: open_pause_settings()
)

pause_achievements_button = Button(
    parent=menu_panel, 
    model='quad', 
    texture='Достижения3.png', 
    scale=(0.4, 0.1), 
    position=(0, -0.1), 
    color=color.white, 
    z=-0.02, 
    enabled=False,
    on_click=lambda: None
)

exit_to_menu_button = Button(
    parent=menu_panel, 
    model='quad', 
    texture='ВыходГМ.png', 
    scale=(0.4, 0.1), 
    position=(0, -0.3), 
    color=color.white, 
    z=-0.02, 
    enabled=False,
    on_click=lambda: show_confirm_exit()
)

def on_continue_hover():
    continue_button.texture = 'ПРигру2.png'

def on_continue_unhover():
    continue_button.texture = 'ПРигру.png'

def on_pause_settings_hover():
    pause_settings_button.texture = 'Настройки4.png'

def on_pause_settings_unhover():
    pause_settings_button.texture = 'Настройки3.png'

def on_pause_achievements_hover():
    pause_achievements_button.texture = 'Достижения4.png'

def on_pause_achievements_unhover():
    pause_achievements_button.texture = 'Достижения3.png'

def on_exit_to_menu_hover():
    exit_to_menu_button.texture = 'ВыходГМ2.png'

def on_exit_to_menu_unhover():
    exit_to_menu_button.texture = 'ВыходГМ.png'

continue_button.on_mouse_enter = on_continue_hover
continue_button.on_mouse_exit = on_continue_unhover
pause_settings_button.on_mouse_enter = on_pause_settings_hover
pause_settings_button.on_mouse_exit = on_pause_settings_unhover
pause_achievements_button.on_mouse_enter = on_pause_achievements_hover
pause_achievements_button.on_mouse_exit = on_pause_achievements_unhover
exit_to_menu_button.on_mouse_enter = on_exit_to_menu_hover
exit_to_menu_button.on_mouse_exit = on_exit_to_menu_unhover

# === ПАНЕЛЬ ПОДТВЕРЖДЕНИЯ ВЫХОДА ===
confirm_panel = Entity(parent=camera.ui, model='quad', scale=(0.7, 0.5), color=color.black66, enabled=False, z=-0.1)
confirm_text = Text(parent=confirm_panel, text="При выходе в меню весь прогресс будет потерян\nи игру придётся начинать заново.\nВы точно хотите выйти в главное меню?", scale=1.5, position=(0, 0.15), origin=(0, 0), color=color.white, enabled=False, background=True, z=-0.15)
confirm_yes_button = Button(parent=confirm_panel, text="Да", scale=(0.2, 0.1), position=(-0.15, -0.1), color=color.green, text_color=color.white, on_click=lambda: confirm_exit_yes(), enabled=False, z=-0.15)
confirm_no_button = Button(parent=confirm_panel, text="Нет", scale=(0.2, 0.1), position=(0.15, -0.1), color=color.red, text_color=color.white, on_click=lambda: confirm_exit_no(), enabled=False, z=-0.15)

def show_confirm_exit():
    global game_paused
    toggle_elements([menu_panel, continue_button, pause_settings_button, pause_achievements_button, exit_to_menu_button], False)
    toggle_elements([confirm_panel, confirm_text, confirm_yes_button, confirm_no_button], True)
    game_paused = True
    mouse.locked = False
    mouse.visible = True
    player.enabled = False

def confirm_exit_yes():
    reset_game()
    toggle_elements([confirm_panel, confirm_text, confirm_yes_button, confirm_no_button], False)
    exit_to_main_menu()

def confirm_exit_no():
    toggle_elements([confirm_panel, confirm_text, confirm_yes_button, confirm_no_button], False)
    toggle_elements([menu_panel, continue_button, pause_settings_button, pause_achievements_button, exit_to_menu_button], True)
    mouse.locked = False
    mouse.visible = True
    player.enabled = False

def exit_to_main_menu():
    global main_menu_active, menu_visible, game_paused, tutorial_active, end_text, end_menu_button
    menu_visible = False
    game_paused = False
    
    # Уничтожаем элементы конца игры
    if end_text:
        destroy(end_text)
        end_text = None
    if end_menu_button:
        destroy(end_menu_button)
        end_menu_button = None
    
    # Очистка всех UI-элементов
    toggle_elements([menu_panel, continue_button, pause_settings_button, pause_achievements_button, exit_to_menu_button], False)
    toggle_elements([settings_panel, settings_title, sound_button, controls_info_button, settings_back], False)
    toggle_elements([controls_info_panel, controls_info_title, controls_info_text, controls_info_back], False)
    toggle_elements([sound_settings_panel, sound_settings_title, sound_volume_text, sound_volume_plus, sound_volume_minus, music_volume_text, music_volume_plus, music_volume_minus, master_volume_text, master_volume_plus, master_volume_minus, sound_settings_back], False)
    tutorial_active = False
    toggle_elements([tutorial_panel, tutorial_text, tutorial_yes_button, tutorial_no_button], False)
    toggle_ui(False)  # Скрываем UI при возврате в главное меню
    reset_game()  # Сбрасываем состояние игры
    main_menu_active = True
    stop_all_music()
    start_menu_music()  # Запускаем музыку меню
    toggle_elements([main_menu_bg, main_menu_panel, play_button, settings_button, achievements_button, exit_button_main], True)
    mouse.locked = False
    mouse.visible = True
    player.enabled = False
    print("Переход в главное меню: end_text и end_menu_button уничтожены")

# === МАГАЗИН ===
shop_items_list = [
    {'image': 'Удобрение2.png', 'price': 2, 'type': 'fertilizer'},
    {'image': 'Саженец2.png', 'price': 10, 'type': 'seedling'},
    {'image': 'ЗолотаяЛейка2.png', 'price': 50, 'type': 'golden_watering_can'},
    {'image': 'ЗачарованнаяУдочка2.png', 'price': 100, 'type': 'enchanted_fishing_rod'}
]

shop_panel = Entity(parent=camera.ui, model='quad', scale=(1.0, 0.8), color=color.black66, enabled=False, z=-0.1)
shop_item1_image = Entity(parent=shop_panel, model='quad', color=color.white, scale=(0.35, 0.5), position=(-0.25, 0.1), z=-0.2, enabled=False)
shop_item2_image = Entity(parent=shop_panel, model='quad', color=color.white, scale=(0.35, 0.5), position=(0.25, 0.1), z=-0.2, enabled=False)
shop_item1_button = Button(parent=shop_panel, text="Купить", scale=(0.25, 0.08), position=(-0.25, -0.25), color=color.green, text_color=color.white, z=-0.2, enabled=False)
shop_item2_button = Button(parent=shop_panel, text="Купить", scale=(0.25, 0.08), position=(0.25, -0.25), color=color.green, text_color=color.white, z=-0.2, enabled=False)
prev_button = Button(parent=shop_panel, model='quad', texture='Стрелка.png', scale=(0.08, 0.08), position=(-0.45, 0.1), color=color.white, rotation_z=180, z=-0.2, on_click=lambda: change_shop_page(-1), enabled=False)
next_button = Button(parent=shop_panel, model='quad', texture='Стрелка.png', scale=(0.08, 0.08), position=(0.45, 0.1), color=color.white, z=-0.2, on_click=lambda: change_shop_page(1), enabled=False)
page_indicator = Text(parent=shop_panel, scale=1.5, position=(0, -0.4), color=color.white, z=-0.2, enabled=False)

# === ПАНЕЛЬ РАЗРАБОТЧИКА ===
dev_panel = Entity(parent=camera.ui, model='cube', scale=(0.6, 0.4, 0.02), color=color.rgba(0, 0, 0, 80), enabled=False, z=-0.1)
dev_title = Text(parent=dev_panel, text='> Консоль', position=(0, 0.15), scale=1.5, color=color.lime, origin=(0, 0))
dev_input = InputField(
    parent=dev_panel,
    scale=(0.6, 0.1),
    position=(0, 0),
    limit_content_to='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ: ',
    placeholder_text='',
    color=color.gray,
    text_origin=(-0.5, 0),
    text_scale=0.8,
    character_limit=50,
    clip_content=True
)
dev_input.highlight_color = color.gray
dev_placeholder = Text(parent=dev_panel, text='> ', position=(-0.28, 0), scale=1.8, color=color.lime, origin=(-1, 0), enabled=True)
dev_apply_button = Button(parent=dev_panel, text='OK', scale=(0.1, 0.08), position=(0, -0.1), color=color.green, text_color=color.white, on_click=lambda: apply_cheat())

# === UI ===
water_text = Text(text=f'Вода у растения: {plant_water}', position=(-0.85, 0.46), scale=1.1, background=True, enabled=False)
food_text = Text(text=f'Еда у растения: {plant_food}', position=(-0.85, 0.36), scale=1.1, background=True, enabled=False)
plant_health_text = Text(text=f'Здоровье растения: {plant_health}', position=(-0.85, 0.26), scale=1.1, background=True, enabled=False)
plant_sign = Text(text='Патиссон\nВыращено: 0%', position=(0.6, -0.4), scale=1.1, background=True, enabled=False)

well_progress_text = Text(text='', position=(0, 0.3), scale=1.5, background=False, enabled=False)

fish_icon = Entity(parent=camera.ui, model='quad', texture='Рыба.png', scale=0.05, position=(-0.82, -0.3), z=-0.01, enabled=False)
fish_text = Text(text=f'{player_fish}', position=(-0.76, -0.29), scale=1.1, background=False, enabled=False)
coins_icon = Entity(parent=camera.ui, model='quad', texture='Монета.png', scale=0.05, position=(-0.82, -0.4), z=-0.01, enabled=False)
coins_text = Text(text=f'{player_coins}', position=(-0.76, -0.39), scale=1.1, background=False, enabled=False)

inventory = ['Лейка', 'Еда', 'Удочка', 'Саженец']
inventory_icons = ['Лейка.png', 'Удобрение.png', 'Удочка.png', 'Саженец.png']
slot_size = 0.1
inventory_slots = []
inventory_counters = []
inventory_shadows = []
selected_border = Entity(parent=camera.ui, model='quad', color=color.azure, scale=(slot_size+0.01, slot_size+0.01), z=-0.01, enabled=False)

for i, icon in enumerate(inventory_icons):
    slot = Button(parent=camera.ui, model='quad', color=color.white66, scale=(slot_size, slot_size), position=(i*slot_size*1.1 - 0.165, -0.43), enabled=False)
    if i == 0:
        watering_can_icon = Entity(parent=slot, model='quad', texture=icon, scale=0.8, z=-0.01)
    elif i == 2:
        fishing_rod_icon = Entity(parent=slot, model='quad', texture=icon, scale=0.8, z=-0.01)
    elif i == 3:
        seedling_icon = Entity(parent=slot, model='quad', texture=icon, scale=0.8, z=-0.01, enabled=False)
    else:
        Entity(parent=slot, model='quad', texture=icon, scale=0.8, z=-0.01)
    inventory_slots.append(slot)
    if i < 2:
        shadow_text = Text(parent=slot, text='0', position=(0.22, -0.22), scale=8, color=color.black, z=-0.01, enabled=False)
        counter_text = Text(parent=slot, text='0', position=(0.2, -0.2), scale=8, color=color.white, alpha=1.0, z=-0.02, enabled=False)
        inventory_counters.append(counter_text)
        inventory_shadows.append(shadow_text)
    else:
        inventory_counters.append(None)
        inventory_shadows.append(None)

# === ФУНКЦИИ ===
def update_inventory_ui():
    selected_border.position = inventory_slots[inventory_index].position
    if inventory_counters[0]:
        inventory_counters[0].text = str(player_water)
        inventory_shadows[0].text = str(player_water)
    if inventory_counters[1]:
        inventory_counters[1].text = str(player_food)
        inventory_shadows[1].text = str(player_food)

def check_map_boundaries():
    if not free_camera_active and player.y < DEATH_Y:
        play_sound('hurt')
        player.position = SPAWN_POSITION
        print("Вы упали! Телепортация обратно...")

def toggle_elements(elements, state):
    for element in elements:
        if element: element.enabled = state

def toggle_ui(state=None):
    global ui_visible
    if state is not None:
        ui_visible = state
    else:
        ui_visible = not ui_visible
    ui_elements = [water_text, food_text, plant_health_text, plant_sign, fish_icon, fish_text, coins_icon, coins_text, selected_border]
    for element in ui_elements:
        if element: element.enabled = ui_visible
    for slot in inventory_slots:
        if slot: slot.enabled = ui_visible
    for counter in inventory_counters:
        if counter: counter.enabled = ui_visible
    for shadow in inventory_shadows:
        if shadow: shadow.enabled = ui_visible
    if hasattr(player, 'cursor') and player.cursor:
        player.cursor.enabled = ui_visible

def toggle_menu():
    global menu_visible, game_paused
    if shop_visible or dev_panel.enabled or free_camera_active or main_menu_active: return
    menu_visible = not menu_visible
    game_paused = menu_visible
    toggle_elements([menu_panel, continue_button, pause_settings_button, pause_achievements_button, exit_to_menu_button], menu_visible)
    player.enabled = not menu_visible
    mouse.locked = not menu_visible
    mouse.visible = menu_visible
    update_inventory_ui()

def toggle_dev_panel():
    global game_paused
    if menu_visible or shop_visible or tutorial_active or main_menu_active: return
    dev_panel.enabled = not dev_panel.enabled
    toggle_elements([dev_title, dev_input, dev_apply_button, dev_placeholder], dev_panel.enabled)
    game_paused = dev_panel.enabled
    if free_camera_active:
        mouse.locked = not dev_panel.enabled
        mouse.visible = dev_panel.enabled
        if not dev_panel.enabled:
            print(f"Консоль закрыта, свободная камера активна, mouse.locked: {mouse.locked}, mouse.position: {mouse.position}")
    else:
        player.enabled = not dev_panel.enabled
        mouse.locked = not dev_panel.enabled
        mouse.visible = dev_panel.enabled
    if dev_panel.enabled:
        mouse.locked = False
        mouse.visible = True
    elif free_camera_active:
        mouse.locked = True
        mouse.visible = False

def validate_cheat(code):
    if not code: return False
    parts = code.split(':')
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else None
    valid_commands = ['givemoney', 'patissonup', 'speedgrowth', 'immortalplant', 'mortalplant', 'cameraon', 'cameraoff', 'setsensitivity']
    if cmd not in valid_commands:
        return False
    if cmd in ['givemoney', 'patissonup', 'speedgrowth', 'setsensitivity'] and not arg:
        return False
    if cmd == 'givemoney':
        try:
            int(arg)
            return True
        except ValueError:
            return False
    if cmd == 'patissonup' and plant:
        try:
            percent = float(arg)
            return 0 <= percent <= 100
        except ValueError:
            return False
    if cmd == 'speedgrowth':
        try:
            multiplier = float(arg)
            return multiplier >= 0
        except ValueError:
            return False
    if cmd == 'setsensitivity':
        try:
            sensitivity = float(arg)
            return sensitivity > 0
        except ValueError:
            return False
    return cmd in ['immortalplant', 'mortalplant', 'cameraon', 'cameraoff']

def apply_cheat():
    global player_coins, plant_growth, growth_speed_multiplier, immortal_plant, plant, free_camera_active, camera_rotation_speed
    code = dev_input.text.strip().lower()
    if not validate_cheat(code):
        dev_input.color = color.red
        dev_input.text = ''
        invoke(lambda: setattr(dev_input, 'color', color.gray), delay=0.5)
        print("Ошибка: неверный код")
        return
    dev_input.color = color.green
    invoke(lambda: setattr(dev_input, 'color', color.gray), delay=0.5)
    parts = code.split(':')
    cmd = parts[0]
    arg = parts[1] if len(parts) > 1 else None
    if cmd == 'givemoney':
        amount = int(arg)
        player_coins += amount
        print(f"Добавлено {amount} монет. Теперь: {player_coins}")
    elif cmd == 'patissonup' and plant:
        percent = float(arg)
        plant_growth = min(100, plant_growth + percent)
        print(f"Рост патиссона увеличен на {percent}%. Теперь: {plant_growth}%")
    elif cmd == 'speedgrowth':
        growth_speed_multiplier = float(arg)
        print(f"Скорость роста установлена в {growth_speed_multiplier}x")
    elif cmd == 'immortalplant' and plant:
        immortal_plant = True
        print("Патиссон теперь бессмертный")
    elif cmd == 'mortalplant':
        immortal_plant = False
        print("Патиссон теперь смертный")
    elif cmd == 'cameraon':
        if not free_camera_active:
            free_camera_active = True
            player.enabled = False
            camera.position = player.position
            camera.rotation = player.rotation
            toggle_ui(False)
            mouse.locked = True
            mouse.visible = False
            mouse.position = (0, 0)
            print(f"Свободная камера включена, mouse.locked: {mouse.locked}, mouse.position: {mouse.position}")
    elif cmd == 'cameraoff':
        if free_camera_active:
            free_camera_active = False
            player.enabled = True
            player.position = camera.position
            player.rotation = camera.rotation
            toggle_ui(True)
            mouse.locked = True
            mouse.visible = False
            print(f"Свободная камера выключена, mouse.locked: {mouse.locked}, mouse.position: {mouse.position}")
    elif cmd == 'setsensitivity':
        camera_rotation_speed = float(arg)
        print(f"Чувствительность мыши установлена: {camera_rotation_speed}")
    dev_input.text = ''
    coins_text.text = f'{player_coins}'
    if plant:
        plant_sign.text = f'Патиссон\nВыращено: {int(plant_growth)}%'

def update_seedling_icon():
    if seedling_icon: seedling_icon.enabled = has_seedling

def update_watering_can_icon():
    if watering_can_icon:
        watering_can_icon.texture = 'ЗолотаяЛейка.png' if has_golden_watering_can else 'Лейка.png'

def update_fishing_rod_icon():
    if fishing_rod_icon:
        fishing_rod_icon.texture = 'ЗачарованнаяУдочка.png' if has_enchanted_fishing_rod else 'Удочка.png'

def buy_item(item_type):
    global player_coins, player_food, player_water, has_seedling, has_golden_watering_can, has_enchanted_fishing_rod, max_water, fishing_clicks_needed
    item_info = next((item for item in shop_items_list if item['type'] == item_type), None)
    if not item_info:
        play_sound('nope')
        return
    conditions = {
        'fertilizer': player_coins >= item_info['price'] and player_food < 50,
        'seedling': player_coins >= item_info['price'] and not has_seedling,
        'golden_watering_can': player_coins >= item_info['price'] and not has_golden_watering_can,
        'enchanted_fishing_rod': player_coins >= item_info['price'] and not has_enchanted_fishing_rod
    }
    if not conditions.get(item_type, False):
        play_sound('nope')
        return
    play_sound('cash')
    player_coins -= item_info['price']
    if item_type == 'fertilizer':
        player_food = min(50, player_food + 10)
    elif item_type == 'seedling':
        has_seedling = True
        update_seedling_icon()
    elif item_type == 'golden_watering_can':
        has_golden_watering_can = True
        max_water = 100
        player_water = min(max_water, player_water)
        update_watering_can_icon()
    elif item_type == 'enchanted_fishing_rod':
        has_enchanted_fishing_rod = True
        fishing_clicks_needed = 5
        update_fishing_rod_icon()
    update_inventory_ui()
    update_shop_display()
    if tutorial_active and tutorial_step == 8 and item_type == 'seedling':
        advance_tutorial()

def update_button_state(button, item):
    conditions = {
        'fertilizer': player_coins >= item['price'] and player_food < 50,
        'seedling': player_coins >= item['price'] and not has_seedling,
        'golden_watering_can': player_coins >= item['price'] and not has_golden_watering_can,
        'enchanted_fishing_rod': player_coins >= item['price'] and not has_enchanted_fishing_rod
    }
    can_buy = conditions.get(item['type'], False)
    button.color = color.green if can_buy else color.gray
    button.text_color = color.white if can_buy else color.dark_gray

def change_shop_page(direction):
    global current_shop_page
    play_sound('click')
    max_pages = (len(shop_items_list) + items_per_page - 1) // items_per_page
    current_shop_page = (current_shop_page + direction) % max_pages
    update_shop_display()

def update_shop_display():
    start_index = current_shop_page * items_per_page
    max_pages = (len(shop_items_list) + items_per_page - 1) // items_per_page
    page_indicator.text = f"{current_shop_page + 1}/{max_pages}"
    if start_index < len(shop_items_list):
        item1 = shop_items_list[start_index]
        shop_item1_image.texture = item1['image']
        shop_item1_image.enabled = True
        shop_item1_button.enabled = True
        shop_item1_button.on_click = Func(buy_item, item1['type'])
        update_button_state(shop_item1_button, item1)
    else:
        shop_item1_image.enabled = False
        shop_item1_button.enabled = False
    if start_index + 1 < len(shop_items_list):
        item2 = shop_items_list[start_index + 1]
        shop_item2_image.texture = item2['image']
        shop_item2_image.enabled = True
        shop_item2_button.enabled = True
        shop_item2_button.on_click = Func(buy_item, item2['type'])
        update_button_state(shop_item2_button, item2)
    else:
        shop_item2_image.enabled = False
        shop_item2_button.enabled = False

def open_shop():
    global shop_visible, game_paused
    if shop_visible or dev_panel.enabled or free_camera_active or main_menu_active or (tutorial_active and tutorial_step not in [2, 3, 8]): return
    play_sound('click')
    shop_visible = game_paused = True
    player.enabled = False
    mouse.locked = False
    mouse.visible = True
    toggle_elements([shop_panel, prev_button, next_button, page_indicator], True)
    update_shop_display()
    if tutorial_active and tutorial_step == 2:
        advance_tutorial()

def close_shop():
    global shop_visible, game_paused
    if not shop_visible: return
    play_sound('click')
    shop_visible = game_paused = False
    player.enabled = True
    mouse.locked = True
    mouse.visible = False
    toggle_elements([shop_panel, shop_item1_image, shop_item2_image, shop_item1_button, shop_item2_button, prev_button, next_button, page_indicator], False)
    if tutorial_active and tutorial_step == 3:
        advance_tutorial()

def switch_time():
    global is_day
    is_day = not is_day
    sky_day.visible = is_day
    sky_night.visible = not is_day
    invoke(switch_time, delay=day_length)

def change_item(index):
    global inventory_index
    inventory_index = index
    update_inventory_ui()

def water_plant():
    global player_water, plant_water
    if player_water >= 10 and plant:
        player_water -= 10
        plant_water = min(100, plant_water + 10)
        update_inventory_ui()
        if tutorial_active and tutorial_step == 10:
            advance_tutorial()

def feed_plant():
    global player_food, plant_food
    if player_food >= 10 and plant:
        player_food -= 10
        plant_food = min(100, plant_food + 10)
        update_inventory_ui()
        if tutorial_active and tutorial_step == 11:
            advance_tutorial()

def start_well_animation():
    global well_active, well_total_rotations, game_paused, well_holding, prev_mouse_angle, well_rotation_time, well_sound_playing
    if well_active or free_camera_active: return
    print("Начинаем работу с колодцем!")
    well_active = True
    well_holding = False
    well_sound_playing = True
    well_total_rotations = 0
    well_rotation_time = 0
    prev_mouse_angle = mouse.x
    game_paused = True
    player.enabled = False
    mouse.locked = False
    mouse.visible = True
    well_progress_text.enabled = True
    well_progress_text.text = "Зажмите ЛКМ на рукояти и крутите мышь!"
    sounds['well'].loop = True
    sounds['well'].play()

def finish_well_animation():
    global well_active, game_paused, player_water, well_holding, well_sound_playing
    well_active = False
    well_holding = False
    well_sound_playing = False
    game_paused = False
    player.enabled = True
    mouse.locked = True
    mouse.visible = False
    well_progress_text.enabled = False
    sounds['well'].stop()
    player_water = max_water
    update_inventory_ui()
    print("Вода набрана!")

def refill_water():
    start_well_animation()

def start_fishing():
    global fishing_active, fishing_clicks, game_paused
    if fishing_active or free_camera_active or (tutorial_active and tutorial_step not in [4, 5, 6]): return
    play_sound('cast_rod')
    fishing_active = True
    fishing_clicks = 0
    game_paused = True
    player.enabled = False
    mouse.locked = False
    mouse.visible = True
    create_fishing_button()
    if tutorial_active and tutorial_step == 4:
        advance_tutorial()

def create_fishing_button():
    global fishing_button
    x, y = random.uniform(-0.8, 0.8), random.uniform(-0.4, 0.4)
    fishing_button = Button(parent=camera.ui, model='circle', color=color.red, scale=0.1, position=(x, y), on_click=fishing_button_clicked)

def fishing_button_clicked():
    global fishing_clicks, fishing_button, player_fish
    fishing_clicks += 1
    if fishing_clicks >= fishing_clicks_needed:
        player_fish += 1
        fish_text.text = f'{player_fish}'
        finish_fishing()
        if tutorial_active and tutorial_step == 5 and player_fish == 1:
            advance_tutorial()
        elif tutorial_active and tutorial_step == 6 and player_fish == 2:
            advance_tutorial()
    else:
        destroy(fishing_button)
        create_fishing_button()

def finish_fishing():
    global fishing_active, fishing_button, game_paused
    if fishing_button:
        destroy(fishing_button)
        fishing_button = None
    play_sound('fishing')
    fishing_active = game_paused = False
    player.enabled = True
    mouse.locked = True
    mouse.visible = False

def sell_fish():
    global player_fish, player_coins
    if player_fish > 0:
        player_fish -= 1
        player_coins += 5
        play_sound('cash')
        if tutorial_active and tutorial_step == 7:
            advance_tutorial()

def plant_plant():
    global plant, field, plant_growth, plant_water, plant_food, plant_health, plant_stage, has_seedling
    if plant or not field or not has_seedling: return
    seedling_model = load_model('Росток.glb')
    plant = Entity(model=seedling_model, position=field.position + (0, 0.5, 0), scale=0.3, collider='box')
    destroy(field)
    field = None
    plant_stage = plant_growth = 0
    plant_water = plant_food = plant_health = 100
    has_seedling = False
    update_seedling_icon()
    if tutorial_active and tutorial_step == 9:
        advance_tutorial()

def remove_plant():
    global plant, field
    if plant:
        destroy(plant)
        plant = None
    play_sound('death')
    field = Entity(model='cube', texture='Грядка.jpg', color=color.brown, scale=(1, 0.1, 1), position=(0, 0.05, 0), collider='box')

def reset_game():
    global player_coins, player_fish, player_water, player_food, max_water, fishing_clicks_needed, has_seedling, has_golden_watering_can, has_enchanted_fishing_rod, plant_growth, plant_water, plant_food, plant_health, plant, field, time_of_day, game_ended, harvest_active, harvest_clicks, end_text, end_menu_button
    player_coins = 0
    player_fish = 0
    player_water = 50
    player_food = 50
    max_water = 50
    fishing_clicks_needed = 10
    has_seedling = False
    has_golden_watering_can = False
    has_enchanted_fishing_rod = False
    plant_growth = 0
    plant_water = 100
    plant_food = 100
    plant_health = 100
    if plant:
        destroy(plant)
        plant = None
    if field is None:
        field = Entity(model='cube', texture='Грядка.jpg', color=color.brown, scale=(1, 0.1, 1), position=(0, 0.05, 0), collider='box')
    time_of_day = 0
    update_inventory_ui()
    update_seedling_icon()
    update_watering_can_icon()
    update_fishing_rod_icon()
    coins_text.text = f'{player_coins}'
    fish_text.text = f'{player_fish}'
    plant_sign.text = 'Патиссон\nВыращено: 0%'
    player.position = SPAWN_POSITION
    game_ended = False
    harvest_active = False
    harvest_clicks = 0
    harvest_text.enabled = False
    if end_text:
        destroy(end_text)
        end_text = None
    if end_menu_button:
        destroy(end_menu_button)
        end_menu_button = None
    mouse.locked = True  # Блокируем курсор при сбросе игры
    mouse.visible = False  # Скрываем курсор

def start_game():
    global main_menu_active, tutorial_active, tutorial_step, game_paused
    reset_game()  # Сбрасываем игру перед началом
    main_menu_active = False
    stop_all_music()
    start_game_music()  # Запускаем игровую музыку
    toggle_elements([main_menu_bg, main_menu_panel, play_button, settings_button, achievements_button, exit_button_main], False)
    toggle_elements([settings_panel, settings_title, sound_button, controls_info_button, settings_back], False)
    toggle_elements([controls_info_panel, controls_info_title, controls_info_text, controls_info_back], False)
    toggle_elements([sound_settings_panel, sound_settings_title, sound_volume_text, sound_volume_plus, sound_volume_minus, music_volume_text, music_volume_plus, music_volume_minus, master_volume_text, master_volume_plus, master_volume_minus, sound_settings_back], False)
    toggle_ui(True)  # Показываем UI при старте игры
    game_paused = True  # Пауза для панели обучения
    player.enabled = False  # Отключаем игрока для взаимодействия с панелью обучения
    mouse.locked = False
    mouse.visible = True
    tutorial_active = True
    tutorial_step = 0
    invoke(lambda: toggle_elements([tutorial_panel, tutorial_text, tutorial_yes_button, tutorial_no_button], True), delay=1)

def advance_tutorial():
    global tutorial_step
    tutorial_step += 1
    update_tutorial()

# === ФУНКЦИЯ СОХРАНЕНИЯ И ЗАГРУЗКИ НАСТРОЕК ===
def save_settings():
    settings = {
        'sound_volume': sound_volume,
        'music_volume': music_volume,
        'master_volume': master_volume
    }
    try:
        with open('settings.json', 'w') as f:
            json.dump(settings, f)
        print("Настройки сохранены")
    except:
        print("Не удалось сохранить настройки")

def load_settings():
    global sound_volume, music_volume, master_volume
    try:
        with open('settings.json', 'r') as f:
            settings = json.load(f)
        sound_volume = settings.get('sound_volume', 1.0)
        music_volume = settings.get('music_volume', 1.0)
        master_volume = settings.get('master_volume', 1.0)
        print(f"Настройки загружены: sound={sound_volume:.2f}, music={music_volume:.2f}, master={master_volume:.2f}")
        update_volumes()  # Применяем загруженные настройки
    except:
        print("Не удалось загрузить настройки, используются значения по умолчанию")

# === МЕНЮ ПАУЗЫ ===
menu_panel = Entity(parent=camera.ui, model='quad', scale=(1.8, 1), color=color.black66, enabled=False, z=-0.1)

continue_button = Button(
    parent=menu_panel, 
    model='quad', 
    texture='ПРигру.png', 
    scale=(0.4, 0.1), 
    position=(0, 0.3), 
    color=color.white, 
    z=-0.02, 
    enabled=False,
    on_click=lambda: toggle_menu()
)

pause_settings_button = Button(
    parent=menu_panel, 
    model='quad', 
    texture='Настройки3.png', 
    scale=(0.4, 0.1), 
    position=(0, 0.1), 
    color=color.white, 
    z=-0.02, 
    enabled=False,
    on_click=lambda: open_pause_settings()
)

pause_achievements_button = Button(
    parent=menu_panel, 
    model='quad', 
    texture='Достижения3.png', 
    scale=(0.4, 0.1), 
    position=(0, -0.1), 
    color=color.white, 
    z=-0.02, 
    enabled=False,
    on_click=lambda: None
)

exit_to_menu_button = Button(
    parent=menu_panel, 
    model='quad', 
    texture='ВыходГМ.png', 
    scale=(0.4, 0.1), 
    position=(0, -0.3), 
    color=color.white, 
    z=-0.02, 
    enabled=False,
    on_click=lambda: show_confirm_exit()
)

def on_continue_hover():
    continue_button.texture = 'ПРигру2.png'

def on_continue_unhover():
    continue_button.texture = 'ПРигру.png'

def on_pause_settings_hover():
    pause_settings_button.texture = 'Настройки4.png'

def on_pause_settings_unhover():
    pause_settings_button.texture = 'Настройки3.png'

def on_pause_achievements_hover():
    pause_achievements_button.texture = 'Достижения4.png'

def on_pause_achievements_unhover():
    pause_achievements_button.texture = 'Достижения3.png'

def on_exit_to_menu_hover():
    exit_to_menu_button.texture = 'ВыходГМ2.png'

def on_exit_to_menu_unhover():
    exit_to_menu_button.texture = 'ВыходГМ.png'

continue_button.on_mouse_enter = on_continue_hover
continue_button.on_mouse_exit = on_continue_unhover
pause_settings_button.on_mouse_enter = on_pause_settings_hover
pause_settings_button.on_mouse_exit = on_pause_settings_unhover
pause_achievements_button.on_mouse_enter = on_pause_achievements_hover
pause_achievements_button.on_mouse_exit = on_pause_achievements_unhover
exit_to_menu_button.on_mouse_enter = on_exit_to_menu_hover
exit_to_menu_button.on_mouse_exit = on_exit_to_menu_unhover

# === ПАНЕЛЬ ПОДТВЕРЖДЕНИЯ ВЫХОДА ===
confirm_panel = Entity(parent=camera.ui, model='quad', scale=(0.7, 0.5), color=color.black66, enabled=False, z=-0.1)
confirm_text = Text(parent=confirm_panel, text="При выходе в меню весь прогресс будет потерян\nи игру придётся начинать заново.\nВы точно хотите выйти в главное меню?", scale=1.5, position=(0, 0.15), origin=(0, 0), color=color.white, enabled=False, background=True, z=-0.15)
confirm_yes_button = Button(parent=confirm_panel, text="Да", scale=(0.2, 0.1), position=(-0.15, -0.1), color=color.green, text_color=color.white, on_click=lambda: confirm_exit_yes(), enabled=False, z=-0.15)
confirm_no_button = Button(parent=confirm_panel, text="Нет", scale=(0.2, 0.1), position=(0.15, -0.1), color=color.red, text_color=color.white, on_click=lambda: confirm_exit_no(), enabled=False, z=-0.15)

def show_confirm_exit():
    global game_paused
    toggle_elements([menu_panel, continue_button, pause_settings_button, pause_achievements_button, exit_to_menu_button], False)
    toggle_elements([confirm_panel, confirm_text, confirm_yes_button, confirm_no_button], True)
    game_paused = True
    mouse.locked = False
    mouse.visible = True
    player.enabled = False

def confirm_exit_yes():
    reset_game()
    toggle_elements([confirm_panel, confirm_text, confirm_yes_button, confirm_no_button], False)
    exit_to_main_menu()

def confirm_exit_no():
    toggle_elements([confirm_panel, confirm_text, confirm_yes_button, confirm_no_button], False)
    toggle_elements([menu_panel, continue_button, pause_settings_button, pause_achievements_button, exit_to_menu_button], True)
    mouse.locked = False
    mouse.visible = True
    player.enabled = False

def exit_to_main_menu():
    global main_menu_active, menu_visible, game_paused, tutorial_active, end_text, end_menu_button
    menu_visible = False
    game_paused = False
    
    # Уничтожаем элементы конца игры
    if end_text:
        destroy(end_text)
        end_text = None
    if end_menu_button:
        destroy(end_menu_button)
        end_menu_button = None
    
    # Очистка всех UI-элементов
    toggle_elements([menu_panel, continue_button, pause_settings_button, pause_achievements_button, exit_to_menu_button], False)
    toggle_elements([settings_panel, settings_title, sound_button, controls_info_button, settings_back], False)
    toggle_elements([controls_info_panel, controls_info_title, controls_info_text, controls_info_back], False)
    toggle_elements([sound_settings_panel, sound_settings_title, sound_volume_text, sound_volume_plus, sound_volume_minus, music_volume_text, music_volume_plus, music_volume_minus, master_volume_text, master_volume_plus, master_volume_minus, sound_settings_back], False)
    tutorial_active = False
    toggle_elements([tutorial_panel, tutorial_text, tutorial_yes_button, tutorial_no_button], False)
    toggle_ui(False)  # Скрываем UI при возврате в главное меню
    reset_game()  # Сбрасываем состояние игры
    main_menu_active = True
    stop_all_music()
    start_menu_music()  # Запускаем музыку меню
    toggle_elements([main_menu_bg, main_menu_panel, play_button, settings_button, achievements_button, exit_button_main], True)
    mouse.locked = False
    mouse.visible = True
    player.enabled = False
    print("Переход в главное меню: end_text и end_menu_button уничтожены")

# === МАГАЗИН ===
shop_items_list = [
    {'image': 'Удобрение2.png', 'price': 2, 'type': 'fertilizer'},
    {'image': 'Саженец2.png', 'price': 10, 'type': 'seedling'},
    {'image': 'ЗолотаяЛейка2.png', 'price': 50, 'type': 'golden_watering_can'},
    {'image': 'ЗачарованнаяУдочка2.png', 'price': 100, 'type': 'enchanted_fishing_rod'}
]

shop_panel = Entity(parent=camera.ui, model='quad', scale=(1.0, 0.8), color=color.black66, enabled=False, z=-0.1)
shop_item1_image = Entity(parent=shop_panel, model='quad', color=color.white, scale=(0.35, 0.5), position=(-0.25, 0.1), z=-0.2, enabled=False)
shop_item2_image = Entity(parent=shop_panel, model='quad', color=color.white, scale=(0.35, 0.5), position=(0.25, 0.1), z=-0.2, enabled=False)
shop_item1_button = Button(parent=shop_panel, text="Купить", scale=(0.25, 0.08), position=(-0.25, -0.25), color=color.green, text_color=color.white, z=-0.2, enabled=False)
shop_item2_button = Button(parent=shop_panel, text="Купить", scale=(0.25, 0.08), position=(0.25, -0.25), color=color.green, text_color=color.white, z=-0.2, enabled=False)
prev_button = Button(parent=shop_panel, model='quad', texture='Стрелка.png', scale=(0.08, 0.08), position=(-0.45, 0.1), color=color.white, rotation_z=180, z=-0.2, on_click=lambda: change_shop_page(-1), enabled=False)
next_button = Button(parent=shop_panel, model='quad', texture='Стрелка.png', scale=(0.08, 0.08), position=(0.45, 0.1), color=color.white, z=-0.2, on_click=lambda: change_shop_page(1), enabled=False)
page_indicator = Text(parent=shop_panel, scale=1.5, position=(0, -0.4), color=color.white, z=-0.2, enabled=False)

# === ПАНЕЛЬ РАЗРАБОТЧИКА ===
dev_panel = Entity(parent=camera.ui, model='cube', scale=(0.6, 0.4, 0.02), color=color.rgba(0, 0, 0, 80), enabled=False, z=-0.1)
dev_title = Text(parent=dev_panel, text='> Консоль', position=(0, 0.15), scale=1.5, color=color.lime, origin=(0, 0))
dev_input = InputField(
    parent=dev_panel,
    scale=(0.6, 0.1),
    position=(0, 0),
    limit_content_to='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ: ',
    placeholder_text='',
    color=color.gray,
    text_origin=(-0.5, 0),
    text_scale=0.8,
    character_limit=50,
    clip_content=True
)
dev_input.highlight_color = color.gray
dev_placeholder = Text(parent=dev_panel, text='> ', position=(-0.28, 0), scale=1.8, color=color.lime, origin=(-1, 0), enabled=True)
dev_apply_button = Button(parent=dev_panel, text='OK', scale=(0.1, 0.08), position=(0, -0.1), color=color.green, text_color=color.white, on_click=lambda: apply_cheat())

# === UI ===
water_text = Text(text=f'Вода у растения: {plant_water}', position=(-0.85, 0.46), scale=1.1, background=True, enabled=False)
food_text = Text(text=f'Еда у растения: {plant_food}', position=(-0.85, 0.36), scale=1.1, background=True, enabled=False)
plant_health_text = Text(text=f'Здоровье растения: {plant_health}', position=(-0.85, 0.26), scale=1.1, background=True, enabled=False)
plant_sign = Text(text='Патиссон\nВыращено: 0%', position=(0.6, -0.4), scale=1.1, background=True, enabled=False)

well_progress_text = Text(text='', position=(0, 0.3), scale=1.5, background=False, enabled=False)

fish_icon = Entity(parent=camera.ui, model='quad', texture='Рыба.png', scale=0.05, position=(-0.82, -0.3), z=-0.01, enabled=False)
fish_text = Text(text=f'{player_fish}', position=(-0.76, -0.29), scale=1.1, background=False, enabled=False)
coins_icon = Entity(parent=camera.ui, model='quad', texture='Монета.png', scale=0.05, position=(-0.82, -0.4), z=-0.01, enabled=False)
coins_text = Text(text=f'{player_coins}', position=(-0.76, -0.39), scale=1.1, background=False, enabled=False)

inventory = ['Лейка', 'Еда', 'Удочка', 'Саженец']
inventory_icons = ['Лейка.png', 'Удобрение.png', 'Удочка.png', 'Саженец.png']
slot_size = 0.1
inventory_slots = []
inventory_counters = []
inventory_shadows = []
selected_border = Entity(parent=camera.ui, model='quad', color=color.azure, scale=(slot_size+0.01, slot_size+0.01), z=-0.01, enabled=False)

for i, icon in enumerate(inventory_icons):
    slot = Button(parent=camera.ui, model='quad', color=color.white66, scale=(slot_size, slot_size), position=(i*slot_size*1.1 - 0.165, -0.43), enabled=False)
    if i == 0:
        watering_can_icon = Entity(parent=slot, model='quad', texture=icon, scale=0.8, z=-0.01)
    elif i == 2:
        fishing_rod_icon = Entity(parent=slot, model='quad', texture=icon, scale=0.8, z=-0.01)
    elif i == 3:
        seedling_icon = Entity(parent=slot, model='quad', texture=icon, scale=0.8, z=-0.01, enabled=False)
    else:
        Entity(parent=slot, model='quad', texture=icon, scale=0.8, z=-0.01)
    inventory_slots.append(slot)
    if i < 2:
        shadow_text = Text(parent=slot, text='0', position=(0.22, -0.22), scale=8, color=color.black, z=-0.01, enabled=False)
        counter_text = Text(parent=slot, text='0', position=(0.2, -0.2), scale=8, color=color.white, alpha=1.0, z=-0.02, enabled=False)
        inventory_counters.append(counter_text)
        inventory_shadows.append(shadow_text)
    else:
        inventory_counters.append(None)
        inventory_shadows.append(None)

# === ФУНКЦИИ ===
def update_inventory_ui():
    selected_border.position = inventory_slots[inventory_index].position
    if inventory_counters[0]:
        inventory_counters[0].text = str(player_water)
        inventory_shadows[0].text = str(player_water)
    if inventory_counters[1]:
        inventory_counters[1].text = str(player_food)
        inventory_shadows[1].text = str(player_food)

def check_map_boundaries():
    if not free_camera_active and player.y < DEATH_Y:
        play_sound('hurt')
        player.position = SPAWN_POSITION
        print("Вы упали! Телепортация обратно...")

def toggle_elements(elements, state):
    for element in elements:
        if element: element.enabled = state

def toggle_ui(state=None):
    global ui_visible
    if state is not None:
        ui_visible = state
    else:
        ui_visible = not ui_visible
    ui_elements = [water_text, food_text, plant_health_text, plant_sign, fish_icon, fish_text, coins_icon, coins_text, selected_border]
    for element in ui_elements:
        if element: element.enabled = ui_visible
    for slot in inventory_slots:
        if slot: slot.enabled = ui_visible
    for counter in inventory_counters:
        if counter: counter.enabled = ui_visible
    for shadow in inventory_shadows:
        if shadow: shadow.enabled = ui_visible
    if hasattr(player, 'cursor') and player.cursor:
        player.cursor.enabled = ui_visible

def toggle_menu():
    global menu_visible, game_paused
    if shop_visible or dev_panel.enabled or free_camera_active or main_menu_active: return
    menu_visible = not menu_visible
    game_paused = menu_visible
    toggle_elements([menu_panel, continue_button, pause_settings_button, pause_achievements_button, exit_to_menu_button], menu_visible)
    player.enabled = not menu_visible
    mouse.locked = not menu_visible
    mouse.visible = menu_visible
    update_inventory_ui()

def toggle_dev_panel():
    global game_paused
    if menu_visible or shop_visible or tutorial_active or main_menu_active: return
    dev_panel.enabled = not dev_panel.enabled
    toggle_elements([dev_title, dev_input, dev_apply_button, dev_placeholder], dev_panel.enabled)
    game_paused = dev_panel.enabled
    if free_camera_active:
        mouse.locked = not dev_panel.enabled
        mouse.visible = dev_panel.enabled
        if not dev_panel.enabled:
            print(f"Консоль закрыта, свободная камера активна, mouse.locked: {mouse.locked}, mouse.position: {mouse.position}")
    else:
        player.enabled = not dev_panel.enabled
        mouse.locked = not dev_panel.enabled
        mouse.visible = dev_panel.enabled
    if dev_panel.enabled:
        mouse.locked = False
        mouse.visible = True
    elif free_camera_active:
        mouse.locked = True
        mouse.visible = False

def validate_cheat(code):
    if not code: return False
    parts = code.split(':')
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else None
    valid_commands = ['givemoney', 'patissonup', 'speedgrowth', 'immortalplant', 'mortalplant', 'cameraon', 'cameraoff', 'setsensitivity']
    if cmd not in valid_commands:
        return False
    if cmd in ['givemoney', 'patissonup', 'speedgrowth', 'setsensitivity'] and not arg:
        return False
    if cmd == 'givemoney':
        try:
            int(arg)
            return True
        except ValueError:
            return False
    if cmd == 'patissonup' and plant:
        try:
            percent = float(arg)
            return 0 <= percent <= 100
        except ValueError:
            return False
    if cmd == 'speedgrowth':
        try:
            multiplier = float(arg)
            return multiplier >= 0
        except ValueError:
            return False
    if cmd == 'setsensitivity':
        try:
            sensitivity = float(arg)
            return sensitivity > 0
        except ValueError:
            return False
    return cmd in ['immortalplant', 'mortalplant', 'cameraon', 'cameraoff']

def apply_cheat():
    global player_coins, plant_growth, growth_speed_multiplier, immortal_plant, plant, free_camera_active, camera_rotation_speed
    code = dev_input.text.strip().lower()
    if not validate_cheat(code):
        dev_input.color = color.red
        dev_input.text = ''
        invoke(lambda: setattr(dev_input, 'color', color.gray), delay=0.5)
        print("Ошибка: неверный код")
        return
    dev_input.color = color.green
    invoke(lambda: setattr(dev_input, 'color', color.gray), delay=0.5)
    parts = code.split(':')
    cmd = parts[0]
    arg = parts[1] if len(parts) > 1 else None
    if cmd == 'givemoney':
        amount = int(arg)
        player_coins += amount
        print(f"Добавлено {amount} монет. Теперь: {player_coins}")
    elif cmd == 'patissonup' and plant:
        percent = float(arg)
        plant_growth = min(100, plant_growth + percent)
        print(f"Рост патиссона увеличен на {percent}%. Теперь: {plant_growth}%")
    elif cmd == 'speedgrowth':
        growth_speed_multiplier = float(arg)
        print(f"Скорость роста установлена в {growth_speed_multiplier}x")
    elif cmd == 'immortalplant' and plant:
        immortal_plant = True
        print("Патиссон теперь бессмертный")
    elif cmd == 'mortalplant':
        immortal_plant = False
        print("Патиссон теперь смертный")
    elif cmd == 'cameraon':
        if not free_camera_active:
            free_camera_active = True
            player.enabled = False
            camera.position = player.position
            camera.rotation = player.rotation
            toggle_ui(False)
            mouse.locked = True
            mouse.visible = False
            mouse.position = (0, 0)
            print(f"Свободная камера включена, mouse.locked: {mouse.locked}, mouse.position: {mouse.position}")
    elif cmd == 'cameraoff':
        if free_camera_active:
            free_camera_active = False
            player.enabled = True
            player.position = camera.position
            player.rotation = camera.rotation
            toggle_ui(True)
            mouse.locked = True
            mouse.visible = False
            print(f"Свободная камера выключена, mouse.locked: {mouse.locked}, mouse.position: {mouse.position}")
    elif cmd == 'setsensitivity':
        camera_rotation_speed = float(arg)
        print(f"Чувствительность мыши установлена: {camera_rotation_speed}")
    dev_input.text = ''
    coins_text.text = f'{player_coins}'
    if plant:
        plant_sign.text = f'Патиссон\nВыращено: {int(plant_growth)}%'

def update_seedling_icon():
    if seedling_icon: seedling_icon.enabled = has_seedling

def update_watering_can_icon():
    if watering_can_icon:
        watering_can_icon.texture = 'ЗолотаяЛейка.png' if has_golden_watering_can else 'Лейка.png'

def update_fishing_rod_icon():
    if fishing_rod_icon:
        fishing_rod_icon.texture = 'ЗачарованнаяУдочка.png' if has_enchanted_fishing_rod else 'Удочка.png'

def buy_item(item_type):
    global player_coins, player_food, player_water, has_seedling, has_golden_watering_can, has_enchanted_fishing_rod, max_water, fishing_clicks_needed
    item_info = next((item for item in shop_items_list if item['type'] == item_type), None)
    if not item_info:
        play_sound('nope')
        return
    conditions = {
        'fertilizer': player_coins >= item_info['price'] and player_food < 50,
        'seedling': player_coins >= item_info['price'] and not has_seedling,
        'golden_watering_can': player_coins >= item_info['price'] and not has_golden_watering_can,
        'enchanted_fishing_rod': player_coins >= item_info['price'] and not has_enchanted_fishing_rod
    }
    if not conditions.get(item_type, False):
        play_sound('nope')
        return
    play_sound('cash')
    player_coins -= item_info['price']
    if item_type == 'fertilizer':
        player_food = min(50, player_food + 10)
    elif item_type == 'seedling':
        has_seedling = True
        update_seedling_icon()
    elif item_type == 'golden_watering_can':
        has_golden_watering_can = True
        max_water = 100
        player_water = min(max_water, player_water)
        update_watering_can_icon()
    elif item_type == 'enchanted_fishing_rod':
        has_enchanted_fishing_rod = True
        fishing_clicks_needed = 5
        update_fishing_rod_icon()
    update_inventory_ui()
    update_shop_display()
    if tutorial_active and tutorial_step == 8 and item_type == 'seedling':
        advance_tutorial()

def update_button_state(button, item):
    conditions = {
        'fertilizer': player_coins >= item['price'] and player_food < 50,
        'seedling': player_coins >= item['price'] and not has_seedling,
        'golden_watering_can': player_coins >= item['price'] and not has_golden_watering_can,
        'enchanted_fishing_rod': player_coins >= item['price'] and not has_enchanted_fishing_rod
    }
    can_buy = conditions.get(item['type'], False)
    button.color = color.green if can_buy else color.gray
    button.text_color = color.white if can_buy else color.dark_gray

def change_shop_page(direction):
    global current_shop_page
    play_sound('click')
    max_pages = (len(shop_items_list) + items_per_page - 1) // items_per_page
    current_shop_page = (current_shop_page + direction) % max_pages
    update_shop_display()

def update_shop_display():
    start_index = current_shop_page * items_per_page
    max_pages = (len(shop_items_list) + items_per_page - 1) // items_per_page
    page_indicator.text = f"{current_shop_page + 1}/{max_pages}"
    if start_index < len(shop_items_list):
        item1 = shop_items_list[start_index]
        shop_item1_image.texture = item1['image']
        shop_item1_image.enabled = True
        shop_item1_button.enabled = True
        shop_item1_button.on_click = Func(buy_item, item1['type'])
        update_button_state(shop_item1_button, item1)
    else:
        shop_item1_image.enabled = False
        shop_item1_button.enabled = False
    if start_index + 1 < len(shop_items_list):
        item2 = shop_items_list[start_index + 1]
        shop_item2_image.texture = item2['image']
        shop_item2_image.enabled = True
        shop_item2_button.enabled = True
        shop_item2_button.on_click = Func(buy_item, item2['type'])
        update_button_state(shop_item2_button, item2)
    else:
        shop_item2_image.enabled = False
        shop_item2_button.enabled = False

def open_shop():
    global shop_visible, game_paused
    if shop_visible or dev_panel.enabled or free_camera_active or main_menu_active or (tutorial_active and tutorial_step not in [2, 3, 8]): return
    play_sound('click')
    shop_visible = game_paused = True
    player.enabled = False
    mouse.locked = False
    mouse.visible = True
    toggle_elements([shop_panel, prev_button, next_button, page_indicator], True)
    update_shop_display()
    if tutorial_active and tutorial_step == 2:
        advance_tutorial()

def close_shop():
    global shop_visible, game_paused
    if not shop_visible: return
    play_sound('click')
    shop_visible = game_paused = False
    player.enabled = True
    mouse.locked = True
    mouse.visible = False
    toggle_elements([shop_panel, shop_item1_image, shop_item2_image, shop_item1_button, shop_item2_button, prev_button, next_button, page_indicator], False)
    if tutorial_active and tutorial_step == 3:
        advance_tutorial()

def switch_time():
    global is_day
    is_day = not is_day
    sky_day.visible = is_day
    sky_night.visible = not is_day
    invoke(switch_time, delay=day_length)

def change_item(index):
    global inventory_index
    inventory_index = index
    update_inventory_ui()

def water_plant():
    global player_water, plant_water
    if player_water >= 10 and plant:
        player_water -= 10
        plant_water = min(100, plant_water + 10)
        update_inventory_ui()
        if tutorial_active and tutorial_step == 10:
            advance_tutorial()

def feed_plant():
    global player_food, plant_food
    if player_food >= 10 and plant:
        player_food -= 10
        plant_food = min(100, plant_food + 10)
        update_inventory_ui()
        if tutorial_active and tutorial_step == 11:
            advance_tutorial()

def start_well_animation():
    global well_active, well_total_rotations, game_paused, well_holding, prev_mouse_angle, well_rotation_time, well_sound_playing
    if well_active or free_camera_active: return
    print("Начинаем работу с колодцем!")
    well_active = True
    well_holding = False
    well_sound_playing = True
    well_total_rotations = 0
    well_rotation_time = 0
    prev_mouse_angle = mouse.x
    game_paused = True
    player.enabled = False
    mouse.locked = False
    mouse.visible = True
    well_progress_text.enabled = True
    well_progress_text.text = "Зажмите ЛКМ на рукояти и крутите мышь!"
    sounds['well'].loop = True
    sounds['well'].play()

def finish_well_animation():
    global well_active, game_paused, player_water, well_holding, well_sound_playing
    well_active = False
    well_holding = False
    well_sound_playing = False
    game_paused = False
    player.enabled = True
    mouse.locked = True
    mouse.visible = False
    well_progress_text.enabled = False
    sounds['well'].stop()
    player_water = max_water
    update_inventory_ui()
    print("Вода набрана!")

def refill_water():
    start_well_animation()

def start_fishing():
    global fishing_active, fishing_clicks, game_paused
    if fishing_active or free_camera_active or (tutorial_active and tutorial_step not in [4, 5, 6]): return
    play_sound('cast_rod')
    fishing_active = True
    fishing_clicks = 0
    game_paused = True
    player.enabled = False
    mouse.locked = False
    mouse.visible = True
    create_fishing_button()
    if tutorial_active and tutorial_step == 4:
        advance_tutorial()

def create_fishing_button():
    global fishing_button
    x, y = random.uniform(-0.8, 0.8), random.uniform(-0.4, 0.4)
    fishing_button = Button(parent=camera.ui, model='circle', color=color.red, scale=0.1, position=(x, y), on_click=fishing_button_clicked)

def fishing_button_clicked():
    global fishing_clicks, fishing_button, player_fish
    fishing_clicks += 1
    if fishing_clicks >= fishing_clicks_needed:
        player_fish += 1
        fish_text.text = f'{player_fish}'
        finish_fishing()
        if tutorial_active and tutorial_step == 5 and player_fish == 1:
            advance_tutorial()
        elif tutorial_active and tutorial_step == 6 and player_fish == 2:
            advance_tutorial()
    else:
        destroy(fishing_button)
        create_fishing_button()

def finish_fishing():
    global fishing_active, fishing_button, game_paused
    if fishing_button:
        destroy(fishing_button)
        fishing_button = None
    play_sound('fishing')
    fishing_active = game_paused = False
    player.enabled = True
    mouse.locked = True
    mouse.visible = False

def sell_fish():
    global player_fish, player_coins
    if player_fish > 0:
        player_fish -= 1
        player_coins += 5
        play_sound('cash')
        if tutorial_active and tutorial_step == 7:
            advance_tutorial()

def plant_plant():
    global plant, field, plant_growth, plant_water, plant_food, plant_health, plant_stage, has_seedling
    if plant or not field or not has_seedling: return
    seedling_model = load_model('Росток.glb')
    plant = Entity(model=seedling_model, position=field.position + (0, 0.5, 0), scale=0.3, collider='box')
    destroy(field)
    field = None
    plant_stage = plant_growth = 0
    plant_water = plant_food = plant_health = 100
    has_seedling = False
    update_seedling_icon()
    if tutorial_active and tutorial_step == 9:
        advance_tutorial()

def remove_plant():
    global plant, field
    if plant:
        destroy(plant)
        plant = None
    play_sound('death')
    field = Entity(model='cube', texture='Грядка.jpg', color=color.brown, scale=(1, 0.1, 1), position=(0, 0.05, 0), collider='box')

def reset_game():
    global player_coins, player_fish, player_water, player_food, max_water, fishing_clicks_needed, has_seedling, has_golden_watering_can, has_enchanted_fishing_rod, plant_growth, plant_water, plant_food, plant_health, plant, field, time_of_day, game_ended, harvest_active, harvest_clicks, end_text, end_menu_button
    player_coins = 0
    player_fish = 0
    player_water = 50
    player_food = 50
    max_water = 50
    fishing_clicks_needed = 10
    has_seedling = False
    has_golden_watering_can = False
    has_enchanted_fishing_rod = False
    plant_growth = 0
    plant_water = 100
    plant_food = 100
    plant_health = 100
    if plant:
        destroy(plant)
        plant = None
    if field is None:
        field = Entity(model='cube', texture='Грядка.jpg', color=color.brown, scale=(1, 0.1, 1), position=(0, 0.05, 0), collider='box')
    time_of_day = 0
    update_inventory_ui()
    update_seedling_icon()
    update_watering_can_icon()
    update_fishing_rod_icon()
    coins_text.text = f'{player_coins}'
    fish_text.text = f'{player_fish}'
    plant_sign.text = 'Патиссон\nВыращено: 0%'
    player.position = SPAWN_POSITION
    game_ended = False
    harvest_active = False
    harvest_clicks = 0
    harvest_text.enabled = False
    if end_text:
        destroy(end_text)
        end_text = None
    if end_menu_button:
        destroy(end_menu_button)
        end_menu_button = None
    mouse.locked = True  # Блокируем курсор при сбросе игры
    mouse.visible = False  # Скрываем курсор

def start_game():
    global main_menu_active, tutorial_active, tutorial_step, game_paused
    reset_game()  # Сбрасываем игру перед началом
    main_menu_active = False
    stop_all_music()
    start_game_music()  # Запускаем игровую музыку
    toggle_elements([main_menu_bg, main_menu_panel, play_button, settings_button, achievements_button, exit_button_main], False)
    toggle_elements([settings_panel, settings_title, sound_button, controls_info_button, settings_back], False)
    toggle_elements([controls_info_panel, controls_info_title, controls_info_text, controls_info_back], False)
    toggle_elements([sound_settings_panel, sound_settings_title, sound_volume_text, sound_volume_plus, sound_volume_minus, music_volume_text, music_volume_plus, music_volume_minus, master_volume_text, master_volume_plus, master_volume_minus, sound_settings_back], False)
    toggle_ui(True)  # Показываем UI при старте игры
    game_paused = True  # Пауза для панели обучения
    player.enabled = False  # Отключаем игрока для взаимодействия с панелью обучения
    mouse.locked = False
    mouse.visible = True
    tutorial_active = True
    tutorial_step = 0
    invoke(lambda: toggle_elements([tutorial_panel, tutorial_text, tutorial_yes_button, tutorial_no_button], True), delay=1)

def advance_tutorial():
    global tutorial_step
    tutorial_step += 1
    update_tutorial()

def start_harvest():
    global harvest_active, harvest_clicks, game_paused
    if harvest_active or game_ended or not plant or plant_growth < 100: return
    harvest_active = True
    harvest_clicks = 0
    game_paused = True
    player.enabled = False
    mouse.locked = False
    mouse.visible = True
    create_harvest_button()
    print("Начало мини-игры сбора патиссона!")

def create_harvest_button():
    global harvest_button
    if harvest_button:
        destroy(harvest_button)
    x, y = random.uniform(-0.8, 0.8), random.uniform(-0.4, 0.4)
    harvest_button = Button(parent=camera.ui, model='circle', color=color.green, scale=0.1, position=(x, y), on_click=harvest_button_clicked)

def harvest_button_clicked():
    global harvest_clicks, harvest_button
    harvest_clicks += 1
    print(f"Клик по кнопке сбора! Клик {harvest_clicks}/{harvest_clicks_needed}")
    if harvest_clicks >= harvest_clicks_needed:
        finish_harvest()
    else:
        destroy(harvest_button)
        create_harvest_button()

def finish_harvest():
    global harvest_active, game_paused, game_ended, harvest_button, end_text, end_menu_button, plant
    if harvest_button:
        destroy(harvest_button)
        harvest_button = None
    harvest_active = False
    game_paused = False
    player.enabled = True
    mouse.locked = False  # Разблокируем курсор
    mouse.visible = True  # Делаем курсор видимым
    if plant:
        destroy(plant)
        plant = None
    harvest_text.enabled = False
    if end_text:  # Уничтожаем старое сообщение, если оно существует
        destroy(end_text)
        end_text = None
    if end_menu_button:  # Уничтожаем старую кнопку, если она существует
        destroy(end_menu_button)
        end_menu_button = None
    end_text = Text(parent=camera.ui, text="Поздравляем! Патиссон сорван.\nСпасибо за игру!\nТеперь доступна консоль разработчика на F12.", scale=2, position=(0, 0), origin=(0, 0), color=color.green, background=True, z=-0.15)
    end_menu_button = Button(parent=camera.ui, text="В главное меню", scale=(0.3, 0.1), position=(0, -0.25), color=color.red, text_color=color.white, z=-0.15, on_click=lambda: exit_to_main_menu())
    game_ended = True
    print("Патиссон сорван, игра завершена!")

def input(key):
    global well_holding
    if key == key_bindings['dev_panel']:
        toggle_dev_panel()
        return
    if main_menu_active or (tutorial_active and tutorial_step == 0):
        return
    if tutorial_active and tutorial_step == 1:
        if key in [key_bindings['forward'], key_bindings['backward'], key_bindings['left'], key_bindings['right']]:
            advance_tutorial()
        return
    if free_camera_active and not dev_panel.enabled:
        return
    if key == key_bindings['menu']:
        if settings_panel.enabled or sound_settings_panel.enabled or controls_info_panel.enabled:
            return  # Игнорируем ESC в настройках
        if shop_visible:
            close_shop()
        elif dev_panel.enabled:
            toggle_dev_panel()
        else:
            toggle_menu()
    if menu_visible or shop_visible or dev_panel.enabled or settings_panel.enabled or sound_settings_panel.enabled or controls_info_panel.enabled:
        return
    key_actions = {
        key_bindings['watering_can']: lambda: change_item(0),
        key_bindings['fertilizer']: lambda: change_item(1),
        key_bindings['fishing_rod']: lambda: change_item(2),
        key_bindings['seedling']: lambda: change_item(3),
        key_bindings['toggle_ui']: lambda: toggle_ui()
    }
    if key in key_actions and not well_active:
        key_actions[key]()
    elif key == 'left mouse down':
        print(f"ЛКМ нажата! Позиция игрока: {player.position}")
        distance_to_handle = distance(player.position, (8.05, 1.8, 6.4))
        print(f"Расстояние до рукояти: {distance_to_handle}")
        if player.intersects(well_handle_3d).hit and not well_active:
            print("ПОПАЛ В РУКОЯТЬ! Запускаем анимацию колодца!")
            start_well_animation()
        elif distance_to_handle < 5 and not well_active:
            print("Близко к рукояти, принудительно запускаем!")
            start_well_animation()
        elif well_active:
            print("Колодец активен, зажимаем рукоять!")
            well_holding = True
        elif not well_active:
            if inventory_index == 0 and plant and player.intersects(plant).hit:
                water_plant()
            elif inventory_index == 1 and plant and player.intersects(plant).hit:
                feed_plant()
            elif field and player.intersects(field).hit and inventory_index == 3 and has_seedling:
                plant_plant()
            elif inventory_index == 2 and player.intersects(pond_collider).hit:
                start_fishing()
            elif plant and plant_growth >= 100 and player.intersects(plant).hit:
                start_harvest()
    elif key == 'left mouse up' and well_active:
        well_holding = False
    elif key == key_bindings['interact'] and not well_active:
        if player.intersects(shop_trigger).hit:
            open_shop()
        elif player.intersects(fish_seller).hit:
            sell_fish()

def update():
    global plant_health, plant_water, plant_food, plant_growth, time_of_day, well_total_rotations, prev_mouse_angle, well_rotation_time, well_sound_playing, growth_speed_multiplier, immortal_plant
    if main_menu_active or (tutorial_active and tutorial_step == 0) or game_ended:
        return
    check_map_boundaries()
    if game_paused and not fishing_active and not well_active and not dev_panel.enabled and not harvest_active:
        return
    if free_camera_active and not dev_panel.enabled:
        mouse.locked = True
        mouse.visible = False
        mouse_pos = mouse.position
        print(f"Свободная камера, mouse.locked: {mouse.locked}, mouse.position: {mouse_pos}, rotation_x: {camera.rotation_x}, rotation_y: {camera.rotation_y}")
        camera.rotation_x -= mouse_pos.y * camera_rotation_speed * time.dt * 1.5
        camera.rotation_y += mouse_pos.x * camera_rotation_speed * time.dt * 1.5
        camera.rotation_x = max(-90, min(90, camera.rotation_x))
        mouse.position = (0, 0)
        speed = camera_speed * (2 if held_keys['shift'] else 1)
        direction = Vec3(
            held_keys[key_bindings['right']] - held_keys[key_bindings['left']],
            held_keys[key_bindings['jump']] - held_keys['c'],
            held_keys[key_bindings['forward']] - held_keys[key_bindings['backward']]
        ).normalized() * speed * time.dt
        yaw = math.radians(camera.rotation_y)
        pitch = math.radians(camera.rotation_x)
        cos_yaw = math.cos(yaw)
        sin_yaw = math.sin(yaw)
        cos_pitch = math.cos(pitch)
        sin_pitch = math.sin(pitch)
        rotated_direction = Vec3(
            direction.x * cos_yaw + direction.z * sin_yaw,
            direction.y * cos_pitch - direction.z * sin_pitch * cos_yaw + direction.x * sin_pitch * sin_yaw,
            direction.z * cos_pitch * cos_yaw - direction.x * cos_pitch* sin_yaw - direction.y * sin_pitch
        )
        camera.position += rotated_direction
        return
    if well_active:
        is_rotating = False
        if well_holding:
            current_mouse_x = mouse.x
            mouse_diff = current_mouse_x - prev_mouse_angle
            if abs(mouse_diff) > 0.01:
                is_rotating = True
                rotation_amount = abs(mouse_diff) * 15
                well_total_rotations += rotation_amount
                if well_handle_3d:
                    well_handle_3d.rotation_x += rotation_amount * 8
                well_rotation_time += time.dt
                print(f"Вращение: {rotation_amount:.3f}, время: {well_rotation_time:.2f}")
            prev_mouse_angle = current_mouse_x
        required_time = 5.0
        progress = min(well_rotation_time / required_time, 1.0)
        if well_holding and is_rotating:
            well_progress_text.text = ""
        elif not well_holding:
            well_progress_text.text = "Зажмите ЛКМ на рукояти и крутите мышь!"
        if well_rotation_time >= required_time:
            print("Анимация завершена! Набрана вода.")
            finish_well_animation()
        return
    if not fishing_active and not harvest_active:
        time_of_day += time.dt / day_length
        if time_of_day >= 1:
            time_of_day = 0
            sky_day.visible = not sky_day.visible
            sky_night.visible = not sky_night.visible
    if plant:
        if plant_growth < 100:  # Изменения параметров только если рост < 100%
            plant_water -= time.dt * 1.2
            plant_food -= time.dt * 0.8
            if (plant_water <= 0 or plant_food <= 0) and not immortal_plant:
                plant_health -= time.dt * 5
            else:
                plant_health = min(100, plant_health + time.dt * 2)
            plant_growth += (3 / 30) * time.dt * growth_speed_multiplier
            plant_growth = min(100, plant_growth)
        if plant_health <= 0:
            remove_plant()
        elif plant_growth < 100:
            plant_growth += (3 / 30) * time.dt * growth_speed_multiplier
            plant_growth = min(100, plant_growth)
        if plant:
            growth_stages = [
                (30, 'Росток.glb', 0.3, 0.3),
                (60, 'Патиссон.glb', 0.5, 0.5),
                (90, 'Патиссон.glb', 0.7, 0.5),
                (100, 'Патиссон.glb', 1.0, 0.65)
            ]
            for threshold, model, scale, y_pos in growth_stages:
                if plant_growth < threshold:
                    if plant.model != model or plant.scale != scale:
                        plant.model = model
                        plant.scale = scale
                        plant.y = y_pos
                    break
        if plant_growth >= 100 and not harvest_text.enabled:
            harvest_text.enabled = True
        water_text.text = f'Вода у растения: {int(plant_water)}'
        food_text.text = f'Еда у растения: {int(plant_food)}'
        plant_health_text.text = f'Здоровье растения: {int(plant_health)}'
        plant_sign.text = f'Патиссон\nВыращено: {int(plant_growth)}%'
    fish_text.text = f'{player_fish}'
    coins_text.text = f'{player_coins}'

# Инициализация
update_inventory_ui()
invoke(switch_time, delay=day_length)
player_water = 50
player_food = 50

# Загрузка настроек при запуске
load_settings()

# При запуске показываем главное меню с музыкой
mouse.locked = False
mouse.visible = True
player.enabled = False
game_paused = True
start_menu_music()  # Запускаем музыку меню при старте

app.run()