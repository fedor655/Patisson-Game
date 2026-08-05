"""Player-side game state: tools, inventory, money, quests, achievements, saves."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from .farming import CROPS, CROP_ORDER

SAVE_DIR = Path.home() / ".patisson2"
SAVE_PATH = SAVE_DIR / "save.json"      # kept: pre-slot saves live here

SLOTS = (1, 2, 3)
AUTOSAVE = "auto"


def slot_path(slot) -> Path:
    """Where a slot lives. Slot 1 falls back to the old single-save file."""
    if slot == AUTOSAVE:
        return SAVE_DIR / "autosave.json"
    path = SAVE_DIR / f"save{slot}.json"
    if slot == 1 and not path.exists() and SAVE_PATH.exists():
        return SAVE_PATH
    return path


def slot_label(slot) -> str:
    return "Автосохранение" if slot == AUTOSAVE else f"Слот {slot}"


def read_meta(slot) -> dict | None:
    """Just enough of a save to describe it in a list, or None if unusable."""
    path = slot_path(slot)
    if not path.exists():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return blob.get("meta") or {}


def describe(slot) -> str:
    meta = read_meta(slot)
    if meta is None:
        return "пусто"
    day = meta.get("day", 0) + 1
    season = meta.get("season", "")
    coins = meta.get("coins", 0)
    played = int(meta.get("play_time", 0) // 60)
    return f"День {day} · {season} · {coins} мон. · {played} мин"


def any_save() -> bool:
    return any(read_meta(s) is not None for s in (AUTOSAVE,) + SLOTS)


def newest_slot():
    """The slot to offer as "continue", or None."""
    best, best_time = None, -1.0
    for slot in (AUTOSAVE,) + SLOTS:
        path = slot_path(slot)
        if read_meta(slot) is None:
            continue
        stamp = path.stat().st_mtime
        if stamp > best_time:
            best, best_time = slot, stamp
    return best

TOOLS = ("hoe", "can", "seeds", "rod", "basket")
TOOL_NAMES = {
    "hoe": "Мотыга",
    "can": "Лейка",
    "seeds": "Семена",
    "rod": "Удочка",
    "basket": "Корзина",
}

FISH_PRICE = 14


@dataclass
class Upgrades:
    """Tool tiers, 1 to 3. Every level changes how a tool behaves, not just a
    number: the hoe works a wider patch, the can waters neighbours, the rod
    changes the odds at the pond, the basket changes what a harvest yields."""

    hoe: int = 1
    can: int = 1
    rod: int = 1
    basket: int = 1
    fertilizer: bool = False        # unlocks feeding plots
    lantern_oil: bool = False       # brighter lanterns at night

    # --- watering can ---
    @property
    def can_capacity(self) -> float:
        return (8.0, 18.0, 34.0)[self.can - 1]

    @property
    def water_radius(self) -> float:
        """Plots within this distance of the target get watered too."""
        return (0.0, 0.0, 2.4)[self.can - 1]

    # --- hoe ---
    @property
    def till_pattern(self) -> tuple:
        """Offsets, in plot spacings, tilled in one swing."""
        if self.hoe >= 3:
            return tuple((i, j) for i in (-1, 0, 1) for j in (-1, 0, 1))
        if self.hoe == 2:
            return ((-1, 0), (0, 0), (1, 0))
        return ((0, 0),)

    # --- rod ---
    @property
    def bite_speed(self) -> float:
        """Multiplier on how long the fish takes to bite."""
        return (1.0, 0.68, 0.45)[self.rod - 1]

    @property
    def strike_window(self) -> float:
        return (0.95, 1.15, 1.40)[self.rod - 1]

    @property
    def reel_ease(self) -> float:
        """Multiplier on the reel marker's speed; lower is easier."""
        return (1.0, 0.90, 0.78)[self.rod - 1]

    @property
    def luck(self) -> float:
        return (0.0, 0.25, 0.60)[self.rod - 1]

    # --- basket ---
    @property
    def harvest_bonus(self) -> int:
        return (0, 1, 2)[self.basket - 1]

    @property
    def sell_multiplier(self) -> float:
        return (1.0, 1.0, 1.25)[self.basket - 1]

    # Kept so old saves still load.
    @property
    def golden_can(self) -> bool:
        return self.can >= 2

    @property
    def enchanted_rod(self) -> bool:
        return self.rod >= 3


# Tool upgrades: key -> per-level (display name, price, what it changes).
TOOL_TIERS = {
    "hoe": [
        ("Стальная мотыга", 180, "Вскапывает три грядки в ряд за раз."),
        ("Мотыга-веер", 520, "Вскапывает участок 3×3 за раз."),
    ],
    "can": [
        ("Золотая лейка", 220, "Больше воды: 18 вместо 8."),
        ("Лейка-дождевик", 600, "34 воды и поливает соседние грядки."),
    ],
    "rod": [
        ("Крепкая удочка", 200, "Клюёт быстрее, окно подсечки шире."),
        ("Зачарованная удочка", 540, "Метка медленнее, редкая рыба чаще."),
    ],
    "basket": [
        ("Плетёная корзина", 160, "На один плод больше с каждой грядки."),
        ("Корзина коробейника", 480, "Ещё плод и +25% к цене продажи."),
    ],
}

TOOL_LABELS = {"hoe": "мотыга", "can": "лейка", "rod": "удочка",
               "basket": "корзина"}


SHOP_ITEMS = [
    ("seed_patisson", "Семена патиссона", 10, "Главная культура фермы."),
    ("seed_carrot", "Семена моркови", 4, "Быстро растёт, дёшево продаётся."),
    ("seed_tomato", "Семена томата", 8, "Даёт два плода за раз."),
    ("seed_wheat", "Семена пшеницы", 3, "Три колоса с грядки."),
    ("seed_pumpkin", "Семена тыквы", 16, "Осенняя культура. Дорогая."),
    ("fertilizer", "Удобрение", 6, "Питание для растения на грядке."),
    ("ash", "Зола", 9, "Лечит гниль на грядке."),
    ("lantern_oil", "Масло для фонарей", 140, "Фонари горят ярче ночью."),
]


def shop_entries(upgrades) -> list:
    """Consumables, then whichever tool tier each tool is up for next."""
    entries = list(SHOP_ITEMS)
    for key, tiers in TOOL_TIERS.items():
        level = getattr(upgrades, key)
        if level - 1 < len(tiers):
            name, price, desc = tiers[level - 1]
            entries.append((f"tool_{key}", name, price, desc))
    return entries


@dataclass
class Quest:
    key: str
    title: str
    detail: str
    goal: int
    reward: int
    kind: str                  # "harvest" | "fish" | "coins" | "plant"
    target: str = ""
    progress: int = 0
    done: bool = False
    claimed: bool = False


def default_quests() -> list[Quest]:
    return [
        Quest("first_patisson", "Первый патиссон",
              "Вырастите и соберите 1 патиссон.", 1, 40, "harvest", "patisson"),
        Quest("fisher", "Рыбак",
              "Поймайте 5 рыб в пруду.", 5, 55, "fish"),
        Quest("garden", "Огородник",
              "Соберите 12 любых культур.", 12, 90, "harvest", "*"),
        Quest("trader", "Торговец",
              "Накопите 400 монет.", 400, 120, "coins"),
        Quest("harvest_master", "Хозяин фермы",
              "Соберите 6 патиссонов.", 6, 200, "harvest", "patisson"),
        Quest("poultry", "Птичница",
              "Соберите 5 яиц.", 5, 70, "collect", "egg"),
        Quest("dairy", "Молочница",
              "Соберите 3 ведра молока.", 3, 90, "collect", "milk"),
        Quest("cook", "Повар",
              "Приготовьте 3 блюда.", 3, 130, "cook", "*"),
        Quest("baker", "Кондитер",
              "Испеките тыквенный пирог.", 1, 260, "cook", "pie"),
    ]


ACHIEVEMENTS = {
    "first_seed": "Первое зерно — посажено растение",
    "first_harvest": "Первый урожай",
    "patisson_lover": "Собрано 10 патиссонов",
    "angler": "Поймано 20 рыб",
    "rich": "Скоплено 1000 монет",
    "night_owl": "Полночь на ферме",
    "all_crops": "Выращены все пять культур",
    "green_thumb": "10 растущих грядок сразу",
    "first_dish": "Первое блюдо у котла",
    "chef": "Приготовить все пять блюд",
    "farmhand": "Накормить животное",
    "pike_hunter": "Поймать щуку",
    "golden": "Поймать золотую рыбку",
    "ichthyologist": "Поймать все виды рыб",
    "well_rested": "Выспаться в своей кровати",
    "toolmaster": "Улучшить все инструменты до предела",
    "gardener": "Прополоть двадцать грядок",
    "crow_chaser": "Прогнать ворону с грядки",
}


class GameState:
    def __init__(self, cfg):
        self.cfg = cfg
        self.coins = cfg.start_coins
        self.tool_index = 0
        self.seed_index = 0
        self.water = 0.0
        self.fish = 0
        self.total_fish = 0
        self.inventory: dict[str, int] = {
            "seed_patisson": 3,
            "seed_carrot": 2,
            "fertilizer": 1,
        }
        self.upgrades = Upgrades()
        self.quests = default_quests()
        self.achievements: set[str] = set()
        self.notifications: list[list] = []
        self.play_time = 0.0
        # Mirrored from the player each frame so the HUD needs only state.
        self.stamina_frac = 1.0
        self.photo_progress = None
        # Set by the app so unlocks and quests can play their fanfare.
        self.sound = None
        # recipe key -> times cooked, for quests and achievements
        self.cooked: dict[str, int] = {}
        # species key -> (count, total kilos), for value and the journal
        self.fish_log: dict[str, list] = {}

    # ------------------------------------------------------------ inventory

    @property
    def tool(self) -> str:
        return TOOLS[self.tool_index]

    @property
    def seed_key(self) -> str:
        return CROP_ORDER[self.seed_index]

    def cycle_seed(self, delta: int = 1):
        self.seed_index = (self.seed_index + delta) % len(CROP_ORDER)

    def count(self, key: str) -> int:
        return self.inventory.get(key, 0)

    def add_fish(self, species_key: str, kilos: float) -> None:
        entry = self.fish_log.setdefault(species_key, [0, 0.0])
        entry[0] += 1
        entry[1] += kilos
        self.fish += 1
        self.total_fish += 1

    def take_fish(self, n: int = 1) -> bool:
        """Spend fish as a cooking ingredient, cheapest species first."""
        if self.fish < n:
            return False
        from .fishing import BY_KEY
        order = sorted(self.fish_log, key=lambda k: BY_KEY[k].price
                       if k in BY_KEY else 0)
        left = n
        for key in order:
            if left <= 0:
                break
            count, kilos = self.fish_log[key]
            used = min(count, left)
            avg = kilos / max(count, 1)
            self.fish_log[key] = [count - used, kilos - avg * used]
            if self.fish_log[key][0] <= 0:
                del self.fish_log[key]
            left -= used
        self.fish -= n
        return True

    def give(self, key: str, n: int = 1):
        self.inventory[key] = self.inventory.get(key, 0) + n

    def take(self, key: str, n: int = 1) -> bool:
        if self.inventory.get(key, 0) < n:
            return False
        self.inventory[key] -= n
        if self.inventory[key] <= 0:
            del self.inventory[key]
        return True

    def notify(self, text: str, seconds: float = 3.4):
        self.notifications.append([text, seconds])
        if len(self.notifications) > 5:
            self.notifications.pop(0)

    def update_notifications(self, dt: float):
        for n in self.notifications:
            n[1] -= dt
        self.notifications = [n for n in self.notifications if n[1] > 0]

    # ---------------------------------------------------------------- shop

    def buy(self, key: str) -> bool:
        for item_key, name, price, _desc in shop_entries(self.upgrades):
            if item_key != key:
                continue
            if self.coins < price:
                self.notify("Не хватает монет")
                return False
            if key.startswith("tool_"):
                tool = key[5:]
                level = getattr(self.upgrades, tool)
                if level - 1 >= len(TOOL_TIERS[tool]):
                    self.notify("Улучшать больше некуда")
                    return False
                self.coins -= price
                setattr(self.upgrades, tool, level + 1)
                self.notify(f"Куплено: {name}")
                if all(getattr(self.upgrades, t) >= 3 for t in TOOL_TIERS):
                    self.unlock("toolmaster")
                return True
            if key == "lantern_oil":
                if self.upgrades.lantern_oil:
                    self.notify("Уже куплено")
                    return False
                self.coins -= price
                self.upgrades.lantern_oil = True
                self.notify(f"Куплено: {name}")
                return True
            self.coins -= price
            self.give(key, 1)
            if key == "fertilizer":
                self.upgrades.fertilizer = True
            self.notify(f"Куплено: {name}")
            return True
        return False

    def sell_all(self) -> int:
        # Imported here: cooking pulls in the world package, and state is
        # imported long before that is ready.
        from .cooking import DISH_PRICE, item_price
        from .livestock import PRODUCT_PRICE

        sellable = set(CROPS) | set(PRODUCT_PRICE) | set(DISH_PRICE)
        total = 0
        for key in list(self.inventory):
            if key in sellable:
                n = self.inventory.pop(key)
                total += item_price(key) * n
        if self.fish_log:
            from .fishing import BY_KEY
            for key, (count, kilos) in self.fish_log.items():
                species = BY_KEY.get(key)
                if species:
                    total += int(round(species.price * kilos))
            self.fish_log.clear()
            self.fish = 0
        elif self.fish:
            total += self.fish * FISH_PRICE
            self.fish = 0
        total = int(round(total * mult))
        if total:
            self.coins += total
            self.notify(f"Продано на {total} монет")
            if self.coins >= 1000:
                self.unlock("rich")
            self.check_quests()
        else:
            self.notify("Нечего продавать")
        return total

    # -------------------------------------------------------------- quests

    def record(self, kind: str, target: str = "", amount: int = 1):
        for q in self.quests:
            if q.done or q.kind != kind:
                continue
            if q.kind in ("harvest", "collect", "cook") \
                    and q.target not in ("*", target):
                continue
            q.progress += amount
            if q.progress >= q.goal:
                q.done = True
                self.coins += q.reward
                if self.sound:
                    self.sound("achieve", 0.7)
                self.notify(f"Задание выполнено: {q.title} (+{q.reward})")
        self.check_quests()

    def check_quests(self):
        for q in self.quests:
            if q.kind == "coins" and not q.done:
                q.progress = self.coins
                if q.progress >= q.goal:
                    q.done = True
                    self.coins += q.reward
                    self.notify(f"Задание выполнено: {q.title} (+{q.reward})")

    def unlock(self, key: str):
        if key in ACHIEVEMENTS and key not in self.achievements:
            self.achievements.add(key)
            if self.sound:
                self.sound("achieve", 0.75)
            self.notify(f"Достижение: {ACHIEVEMENTS[key]}")

    # ---------------------------------------------------------------- save

    def to_dict(self) -> dict:
        return {
            "version": 2,
            "saved_at": time.time(),
            "coins": self.coins,
            "fish": self.fish,
            "total_fish": self.total_fish,
            "water": self.water,
            "inventory": self.inventory,
            "upgrades": vars(self.upgrades),
            "achievements": sorted(self.achievements),
            "play_time": self.play_time,
            "cooked": self.cooked,
            "fish_log": self.fish_log,
            "quests": [
                {"key": q.key, "progress": q.progress, "done": q.done,
                 "claimed": q.claimed}
                for q in self.quests
            ],
        }

    def from_dict(self, data: dict):
        self.coins = data.get("coins", self.coins)
        self.fish = data.get("fish", 0)
        self.total_fish = data.get("total_fish", 0)
        self.water = data.get("water", 0.0)
        self.inventory = dict(data.get("inventory", {}))
        up = data.get("upgrades", {})
        # Start from defaults: loading a save must not inherit tools bought in
        # whatever run happened to be in memory.
        self.upgrades = Upgrades()
        for key in ("hoe", "can", "rod", "basket"):
            if key in up:
                setattr(self.upgrades, key, max(1, min(3, int(up[key]))))
        for key in ("fertilizer", "lantern_oil"):
            if key in up:
                setattr(self.upgrades, key, bool(up[key]))
        # Saves from before tools had tiers stored booleans instead.
        if "can" not in up and up.get("golden_can"):
            self.upgrades.can = 2
        if "rod" not in up and up.get("enchanted_rod"):
            self.upgrades.rod = 3
        self.achievements = set(data.get("achievements", []))
        self.play_time = data.get("play_time", 0.0)
        self.cooked = dict(data.get("cooked", {}))
        self.fish_log = {k: list(v) for k, v in data.get("fish_log", {}).items()}
        by_key = {q.key: q for q in self.quests}
        for qd in data.get("quests", []):
            q = by_key.get(qd["key"])
            if q:
                q.progress = qd.get("progress", 0)
                q.done = qd.get("done", False)
                q.claimed = qd.get("claimed", False)


def save_game(state: GameState, farm, cycle, player, path: Path = SAVE_PATH,
              livestock=None, pests=None, tutorial=None, slot=None) -> Path:
    if slot is not None:
        path = slot_path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = {
        "meta": {"day": cycle.day, "season": cycle.season_name,
                 "coins": state.coins, "play_time": state.play_time,
                 "clock": cycle.clock_string()},
        "state": state.to_dict(),
        "farm": farm.to_dict(),
        "livestock": livestock.to_dict() if livestock else {},
        "pests": pests.to_dict() if pests else {},
        "tutorial": tutorial.to_dict() if tutorial else {},
        "clock": {"total_time": cycle.total_time},
        "player": {"x": player.pos.x, "y": player.pos.y,
                   "heading": player.heading, "pitch": player.pitch},
    }
    # Write beside the target and swap it in: a crash mid-write must not be
    # able to leave a half-written save where the real one used to be.
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(blob, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_game(state: GameState, farm, cycle, player, path: Path = SAVE_PATH,
              livestock=None, pests=None, tutorial=None, slot=None) -> bool:
    if slot is not None:
        path = slot_path(slot)
    if not path.exists():
        return False
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    state.from_dict(blob.get("state", {}))
    farm.from_dict(blob.get("farm", {}))
    if livestock is not None:
        livestock.from_dict(blob.get("livestock", {}))
    if pests is not None:
        pests.from_dict(blob.get("pests", {}))
    if tutorial is not None:
        tutorial.from_dict(blob.get("tutorial", {}))
    cycle.total_time = blob.get("clock", {}).get("total_time", cycle.total_time)
    p = blob.get("player", {})
    if p:
        player.pos.x = p.get("x", player.pos.x)
        player.pos.y = p.get("y", player.pos.y)
        player.pos.z = player.world.height_at(player.pos.x, player.pos.y)
        player.heading = p.get("heading", player.heading)
        player.pitch = p.get("pitch", player.pitch)
    return True
