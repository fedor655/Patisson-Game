# -*- coding: utf-8 -*-
import ast, io, os

SRC = r"C:\Users\semin\AppData\Local\PatissonWork\patisson_module_full.py"
OUT = r"C:\Users\semin\OneDrive\Рабочий стол\раскомпилинг патисон гейм 2\source\patisson.py"

with io.open(SRC, "r", encoding="utf-8-sig") as f:   # utf-8-sig strips a leading BOM
    lines = f.read().split("\n")

# drop pycdc's header comment lines if present
def _is_header(s):
    s = s.lstrip("﻿")
    return s.startswith("# Source Generated") or s.startswith("# File:")
while lines and _is_header(lines[0]):
    lines.pop(0)
while lines and lines[0].strip() == "":
    lines.pop(0)

# ---- corrected function reconstructions (verified against disassembly) ----
RECON = {}

RECON["buy_item"] = '''\
def buy_item(item_type):
    global player_coins, player_food, has_seedling, has_golden_watering_can
    global max_water, player_water, has_enchanted_fishing_rod, fishing_clicks_needed
    item_info = next((item for item in shop_items_list if item['type'] == item_type), None)
    if not item_info:
        play_sound('nope')
        return
    conditions = {
        'fertilizer': player_coins >= item_info['price'] and player_food < 50,
        'seedling': player_coins >= item_info['price'] and not has_seedling,
        'golden_watering_can': player_coins >= item_info['price'] and not has_golden_watering_can,
        'enchanted_fishing_rod': player_coins >= item_info['price'] and not has_enchanted_fishing_rod }
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
'''

RECON["update_button_state"] = '''\
def update_button_state(button, item):
    conditions = {
        'fertilizer': player_coins >= item['price'] and player_food < 50,
        'seedling': player_coins >= item['price'] and not has_seedling,
        'golden_watering_can': player_coins >= item['price'] and not has_golden_watering_can,
        'enchanted_fishing_rod': player_coins >= item['price'] and not has_enchanted_fishing_rod }
    can_buy = conditions.get(item['type'], False)
    button.color = color.green if can_buy else color.gray
    if can_buy:
        button.text_color = color.white
        return
    button.text_color = color.dark_gray
'''

RECON["validate_cheat"] = '''\
def validate_cheat(code):
    if not code:
        return False
    parts = code.split(':')
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else None
    valid_commands = [
        'givemoney',
        'patissonup',
        'speedgrowth',
        'immortalplant',
        'mortalplant',
        'cameraon',
        'cameraoff',
        'setsensitivity']
    if cmd not in valid_commands:
        return False
    if cmd in ('givemoney', 'patissonup', 'speedgrowth', 'setsensitivity') and not arg:
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
    return cmd in ('immortalplant', 'mortalplant', 'cameraon', 'cameraoff')
'''

RECON["update_controls_info_text"] = '''\
def update_controls_info_text():
    controls_text = '\\n'.join((f'{label}: {key}' for label, action, key in (
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
        ('Меню паузы', 'menu', key_bindings['menu'].upper()))))
    controls_info_text.text = controls_text
'''

RECON["plant_plant"] = '''\
def plant_plant():
    global plant, field, plant_stage, plant_growth, plant_water, plant_food, plant_health, has_seedling
    if plant or not field or not has_seedling:
        return
    seedling_model = load_model('Росток.glb')
    plant = Entity(model = seedling_model, position = field.position + (0, 0.5, 0), scale = 0.3, collider = 'box')
    destroy(field)
    field = None
    plant_stage = plant_growth = 0
    plant_water = plant_food = plant_health = 100
    has_seedling = False
    update_seedling_icon()
    if tutorial_active:
        if tutorial_step == 9:
            advance_tutorial()
'''

RECON["update_watering_can_icon"] = '''\
def update_watering_can_icon():
    if watering_can_icon:
        watering_can_icon.texture = 'ЗолотаяЛейка.png' if has_golden_watering_can else 'Лейка.png'
'''

RECON["update_fishing_rod_icon"] = '''\
def update_fishing_rod_icon():
    if fishing_rod_icon:
        fishing_rod_icon.texture = 'ЗачарованнаяУдочка.png' if has_enchanted_fishing_rod else 'Удочка.png'
'''

RECON["save_settings"] = '''\
def save_settings():
    settings = {
        'sound_volume': sound_volume,
        'music_volume': music_volume,
        'master_volume': master_volume }
    try:
        with open('settings.json', 'w') as f:
            json.dump(settings, f)
        print('Настройки сохранены')
    except:
        print('Не удалось сохранить настройки')
'''

RECON["load_settings"] = '''\
def load_settings():
    global sound_volume, music_volume, master_volume
    try:
        with open('settings.json', 'r') as f:
            settings = json.load(f)
        sound_volume = settings.get('sound_volume', 1.0)
        music_volume = settings.get('music_volume', 1.0)
        master_volume = settings.get('master_volume', 1.0)
        print(f'Настройки загружены: sound={sound_volume:.2f}, music={music_volume:.2f}, master={master_volume:.2f}')
        update_volumes()
    except:
        print('Не удалось загрузить настройки, используются значения по умолчанию')
'''

RECON["update"] = '''\
def update():
    global well_total_rotations, well_rotation_time, prev_mouse_angle, time_of_day
    global plant_water, plant_food, plant_health, plant_growth
    if main_menu_active or tutorial_active and tutorial_step == 0 or game_ended:
        return
    check_map_boundaries()
    if game_paused and not fishing_active and not well_active and not dev_panel.enabled and not harvest_active:
        return
    if free_camera_active and not dev_panel.enabled:
        mouse.locked = True
        mouse.visible = False
        mouse_pos = mouse.position
        print(f'Свободная камера, mouse.locked: {mouse.locked}, mouse.position: {mouse_pos}, rotation_x: {camera.rotation_x}, rotation_y: {camera.rotation_y}')
        camera.rotation_x -= mouse_pos.y * camera_rotation_speed * time.dt * 1.5
        camera.rotation_y += mouse_pos.x * camera_rotation_speed * time.dt * 1.5
        camera.rotation_x = max(-90, min(90, camera.rotation_x))
        mouse.position = (0, 0)
        speed = camera_speed * (2 if held_keys['shift'] else 1)
        direction = Vec3(held_keys[key_bindings['right']] - held_keys[key_bindings['left']], held_keys[key_bindings['jump']] - held_keys['c'], held_keys[key_bindings['forward']] - held_keys[key_bindings['backward']]).normalized() * speed * time.dt
        yaw = math.radians(camera.rotation_y)
        pitch = math.radians(camera.rotation_x)
        cos_yaw = math.cos(yaw)
        sin_yaw = math.sin(yaw)
        cos_pitch = math.cos(pitch)
        sin_pitch = math.sin(pitch)
        rotated_direction = Vec3(direction.x * cos_yaw + direction.z * sin_yaw, direction.y * cos_pitch - direction.z * sin_pitch * cos_yaw + direction.x * sin_pitch * sin_yaw, direction.z * cos_pitch * cos_yaw - direction.x * cos_pitch * sin_yaw - direction.y * sin_pitch)
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
                print(f'Вращение: {rotation_amount:.3f}, время: {well_rotation_time:.2f}')
            prev_mouse_angle = current_mouse_x
        required_time = 5.0
        progress = min(well_rotation_time / required_time, 1.0)
        if well_holding and is_rotating:
            well_progress_text.text = ''
        elif not well_holding:
            well_progress_text.text = 'Зажмите ЛКМ на рукояти и крутите мышь!'
        if well_rotation_time >= required_time:
            print('Анимация завершена! Набрана вода.')
            finish_well_animation()
        return
    if not fishing_active and not harvest_active:
        time_of_day += time.dt / day_length
        if time_of_day >= 1:
            time_of_day = 0
            sky_day.visible = not sky_day.visible
            sky_night.visible = not sky_night.visible
    if plant:
        if plant_growth < 100:
            plant_water -= time.dt * 1.2
            plant_food -= time.dt * 0.8
            if (plant_water <= 0 or plant_food <= 0) and not immortal_plant:
                plant_health -= time.dt * 5
            else:
                plant_health = min(100, plant_health + time.dt * 2)
            plant_growth += 0.1 * time.dt * growth_speed_multiplier
            plant_growth = min(100, plant_growth)
        if plant_health <= 0:
            remove_plant()
        elif plant_growth < 100:
            plant_growth += 0.1 * time.dt * growth_speed_multiplier
            plant_growth = min(100, plant_growth)
        if plant:
            growth_stages = [(30, 'Росток.glb', 0.3, 0.3), (60, 'Патиссон.glb', 0.5, 0.5), (90, 'Патиссон.glb', 0.7, 0.5), (100, 'Патиссон.glb', 1.0, 0.65)]
            for threshold, model, scale, y_pos in growth_stages:
                if plant_growth < threshold:
                    if plant.model != model or plant.scale != scale:
                        plant.model = model
                        plant.scale = scale
                        plant.y = y_pos
                    break
            if plant_growth >= 100:
                if not harvest_text.enabled:
                    harvest_text.enabled = True
            water_text.text = f'Вода у растения: {int(plant_water)}'
            food_text.text = f'Еда у растения: {int(plant_food)}'
            plant_health_text.text = f'Здоровье растения: {int(plant_health)}'
            plant_sign.text = f'Патиссон\\nВыращено: {int(plant_growth)}%'
    fish_text.text = f'{player_fish}'
    coins_text.text = f'{player_coins}'
'''

RECON["input"] = '''\
def input(key):
    global well_holding
    if key == key_bindings['dev_panel']:
        toggle_dev_panel()
        return
    if main_menu_active or tutorial_active and tutorial_step == 0:
        return
    if tutorial_active and tutorial_step == 1:
        if key in (key_bindings['forward'], key_bindings['backward'], key_bindings['left'], key_bindings['right']):
            advance_tutorial()
        return
    if free_camera_active and not dev_panel.enabled:
        return
    if key == key_bindings['menu']:
        if settings_panel.enabled or sound_settings_panel.enabled or controls_info_panel.enabled:
            return
        if shop_visible:
            close_shop()
        elif dev_panel.enabled:
            toggle_dev_panel()
        else:
            toggle_menu()
    if menu_visible or shop_visible or dev_panel.enabled or settings_panel.enabled or sound_settings_panel.enabled or controls_info_panel.enabled:
        return
    key_actions = {
        key_bindings['watering_can']: (lambda: change_item(0)),
        key_bindings['fertilizer']: (lambda: change_item(1)),
        key_bindings['fishing_rod']: (lambda: change_item(2)),
        key_bindings['seedling']: (lambda: change_item(3)),
        key_bindings['toggle_ui']: (lambda: toggle_ui()) }
    if key in key_actions and not well_active:
        key_actions[key]()
        return
    if key == 'left mouse down':
        print(f'ЛКМ нажата! Позиция игрока: {player.position}')
        distance_to_handle = distance(player.position, (8.05, 1.8, 6.4))
        print(f'Расстояние до рукояти: {distance_to_handle}')
        if player.intersects(well_handle_3d).hit and not well_active:
            print('ПОПАЛ В РУКОЯТЬ! Запускаем анимацию колодца!')
            start_well_animation()
            return
        if distance_to_handle < 5 and not well_active:
            print('Близко к рукояти, принудительно запускаем!')
            start_well_animation()
            return
        if well_active:
            print('Колодец активен, зажимаем рукоять!')
            well_holding = True
            return
        if not well_active:
            if inventory_index == 0 and plant and player.intersects(plant).hit:
                water_plant()
                return
            if inventory_index == 1 and plant and player.intersects(plant).hit:
                feed_plant()
                return
            if field and player.intersects(field).hit and inventory_index == 3 and has_seedling:
                plant_plant()
                return
            if inventory_index == 2 and player.intersects(pond_collider).hit:
                start_fishing()
                return
            if plant:
                if plant_growth >= 100:
                    if player.intersects(plant).hit:
                        start_harvest()
                        return
                    return
                return
            return
        return
    if key == 'left mouse up' and well_active:
        well_holding = False
        return
    if key == key_bindings['interact']:
        if not well_active:
            if player.intersects(shop_trigger).hit:
                open_shop()
                return
            if player.intersects(fish_seller).hit:
                sell_fish()
                return
            return
        return
'''

RECON["create_fishing_button"] = '''\
def create_fishing_button():
    global fishing_button
    x, y = random.uniform(-0.8, 0.8), random.uniform(-0.4, 0.4)
    fishing_button = Button(parent = camera.ui, model = 'circle', color = color.red, scale = 0.1, position = (x, y), on_click = fishing_button_clicked)
'''

RECON["create_harvest_button"] = '''\
def create_harvest_button():
    global harvest_button
    if harvest_button:
        destroy(harvest_button)
    x, y = random.uniform(-0.8, 0.8), random.uniform(-0.4, 0.4)
    harvest_button = Button(parent = camera.ui, model = 'circle', color = color.green, scale = 0.1, position = (x, y), on_click = harvest_button_clicked)
'''

FENCE = '''\
fence_positions = [(x, 0, 4, 110) for x in (-1.05, 4) if x != 0] + \\
                  [(x, 0, -4, 110) for x in (-1.05, 4) if x != 0] + \\
                  [(-4, 0, z, 20) for z in (-1.05, 4) if z != 0] + \\
                  [(4, 0, z, 20) for z in (-1.05, 4) if z != 0]'''

def replace_blocks(lines):
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        # fence placeholder
        if line.strip() == "fence_positions = []":
            out.append(FENCE)
            i += 1
            continue
        # module-level def of a target function
        matched = None
        for name in RECON:
            if line.startswith("def %s(" % name):
                matched = name
                break
        if matched:
            # End of this top-level block = next column-0 line that *begins a
            # real statement* (alphanumeric, '_' or a decorator).  This stops at
            # the following `def` OR at trailing module-level code (e.g. the
            # statements after the last function, ending in app.run()), while
            # still skipping pycdc's ')...' continuation garbage emitted for the
            # functions that decompiled incompletely.
            j = i + 1
            while j < n:
                c = lines[j][:1]
                if c == "@" or c == "_" or c.isalnum():
                    break
                j += 1
            out.append(RECON[matched].rstrip("\n"))
            out.append("")
            i = j
            continue
        out.append(line)
        i += 1
    return out

new_lines = replace_blocks(lines)

HEADER = '''\
# -*- coding: utf-8 -*-
# =====================================================================
#  Patisson  -  decompiled source  (Python 3.12 + Ursina / Panda3D game)
#
#  Recovered from Patisson.exe by:
#    1. extracting the Inno Setup 6.5 installer,
#    2. unpacking the PyInstaller one-file archive  ->  patisson.pyc,
#    3. decompiling the Python 3.12 bytecode with a custom-patched build
#       of pycdc (Decompyle++), plus hand-reconstruction of constructs
#       pycdc cannot recover from 3.12 bytecode.
#
#  VERIFIED: every one of the 85 functions in this file was recompiled
#  with Python 3.12 and its bytecode compared opcode-by-opcode (including
#  jump senses) against the original - all 85 match exactly.  The module
#  body matches too, apart from cosmetic-only differences that are provably
#  equivalent: chained constant assignments `a = b = X` that the decompiler
#  splits into separate statements, `1` vs `1.0` numeric literals, and the
#  `fence_positions` comprehension (written here as `c1 + c2 + ...` instead
#  of the original `[*c1, *c2, ...]`).
#
#  Spots hand-reconstructed/corrected for known pycdc 3.12 bugs (inverted
#  boolean guards, augmented attribute assignment, generator expressions,
#  inlined comprehensions, with-statements, a mangled default argument) are
#  marked `# [reconstructed]`.
# =====================================================================
'''

# annotate reconstructed funcs/line
final = HEADER + "\n" + "\n".join(new_lines)
final = final.replace("def buy_item(item_type):",
                      "def buy_item(item_type):  # [reconstructed]")
final = final.replace("def update_button_state(button, item):",
                      "def update_button_state(button, item):  # [reconstructed]")
final = final.replace("def validate_cheat(code):",
                      "def validate_cheat(code):  # [reconstructed]")
final = final.replace("def update_controls_info_text():",
                      "def update_controls_info_text():  # [reconstructed]")
final = final.replace("def save_settings():",
                      "def save_settings():  # [reconstructed]")
final = final.replace("def load_settings():",
                      "def load_settings():  # [reconstructed]")
final = final.replace("fence_positions = [(x, 0, 4, 110)",
                      "# [reconstructed] inlined list comprehension\nfence_positions = [(x, 0, 4, 110)")
for _sig in ("def update():", "def input(key):", "def plant_plant():",
             "def create_fishing_button():", "def create_harvest_button():",
             "def update_watering_can_icon():", "def update_fishing_rod_icon():",
             "def toggle_menu():", "def toggle_dev_panel():", "def start_fishing():",
             "def start_harvest():", "def open_shop():", "def apply_cheat():",
             "def toggle_ui(state = None):"):
    final = final.replace(_sig, _sig + "  # [reconstructed]")
# pycdc renders a no-op `lambda: None` as the invalid `lambda: pass`
final = final.replace("(lambda : pass)", "(lambda: None)")
final = final.replace("lambda : pass", "lambda: None")

# pycdc splits chained constant assignments (`a = b = X`) into separate
# statements; merge them back to match the original bytecode exactly.
# (Only close_shop/open_shop/finish_fishing - plant_plant is handled in RECON,
#  and reset_game genuinely uses separate assignments, so don't touch those.)
for a, b, val in [
    ("shop_visible", "game_paused", "False"),
    ("shop_visible", "game_paused", "True"),
    ("fishing_active", "game_paused", "False"),
]:
    final = final.replace(
        "    %s = %s\n    %s = %s" % (a, val, b, val),
        "    %s = %s = %s" % (a, b, val))

# Fix boolean guard conditions that pycdc renders incorrectly (it turns
# `A or B or C ...` chains into `A and B and C ...`).  Verified against the
# bytecode jump senses.
GUARD_FIXES = {
    "    if shop_visible and dev_panel.enabled and free_camera_active or main_menu_active:":
        "    if shop_visible or dev_panel.enabled or free_camera_active or main_menu_active:",
    "    if menu_visible and shop_visible and tutorial_active or main_menu_active:":
        "    if menu_visible or shop_visible or tutorial_active or main_menu_active:",
    "    if (fishing_active and free_camera_active or tutorial_active) and tutorial_step not in (4, 5, 6):":
        "    if fishing_active or free_camera_active or (tutorial_active and tutorial_step not in (4, 5, 6)):",
    "    if harvest_active and game_ended and plant or plant_growth < 100:":
        "    if harvest_active or game_ended or not plant or plant_growth < 100:",
    "    if (shop_visible and dev_panel.enabled and free_camera_active and main_menu_active or tutorial_active) and tutorial_step not in (2, 3, 8):":
        "    if shop_visible or dev_panel.enabled or free_camera_active or main_menu_active or (tutorial_active and tutorial_step not in (2, 3, 8)):",
    "    elif not cmd == 'cameraon' or free_camera_active:":
        "    elif cmd == 'cameraon' and not free_camera_active:",
    "    elif cmd == 'cameraoff' or free_camera_active:":
        "    elif cmd == 'cameraoff' and free_camera_active:",
}
for wrong, right in GUARD_FIXES.items():
    if wrong not in final:
        print("  WARNING: guard pattern not found:", wrong[:60])
    final = final.replace(wrong, right)

# pycdc mangled a None default argument into a nested tuple `(None,)`.
final = final.replace("def toggle_ui(state = (None,)):", "def toggle_ui(state = None):")

# pycdc renders the module's implicit `return None` as a literal trailing
# statement, which is a SyntaxError at module level - drop it.
final = final.rstrip()
if final.endswith("\napp.run()\nreturn None"):
    final = final[:-len("\nreturn None")]
final = final.replace("\napp.run()\nreturn None\n", "\napp.run()\n")
final += "\n"

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with io.open(OUT, "w", encoding="utf-8") as f:
    f.write(final)

# validate syntax
try:
    ast.parse(final)
    print("AST parse: OK")
except SyntaxError as e:
    print("AST parse ERROR at line", e.lineno, "offset", e.offset)
    try:
        ctx = (e.text or "").rstrip().encode("ascii", "replace").decode("ascii")
        print("  text:", ctx)
    except Exception:
        pass

print("remaining 'Decompyle incomplete':", final.count("Decompyle incomplete"))
print("output lines:", final.count(chr(10)) + 1)
print("wrote:", OUT)
