"""Player-side game state: tools, inventory, money, quests, achievements, saves."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .farming import CROPS, CROP_ORDER

SAVE_DIR = Path.home() / ".patisson2"
SAVE_PATH = SAVE_DIR / "save.json"

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
    golden_can: bool = False        # holds more water
    enchanted_rod: bool = False     # fish bite sooner
    fertilizer: bool = False        # unlocks feeding plots
    lantern_oil: bool = False       # brighter lanterns at night

    @property
    def can_capacity(self) -> float:
        return 20.0 if self.golden_can else 8.0


SHOP_ITEMS = [
    ("seed_patisson", "Семена патиссона", 10, "Главная культура фермы."),
    ("seed_carrot", "Семена моркови", 4, "Быстро растёт, дёшево продаётся."),
    ("seed_tomato", "Семена томата", 8, "Даёт два плода за раз."),
    ("seed_wheat", "Семена пшеницы", 3, "Три колоса с грядки."),
    ("seed_pumpkin", "Семена тыквы", 16, "Осенняя культура. Дорогая."),
    ("fertilizer", "Удобрение", 6, "Питание для растения на грядке."),
    ("golden_can", "Золотая лейка", 220, "Втрое больше воды за один поход."),
    ("enchanted_rod", "Зачарованная удочка", 260, "Рыба клюёт заметно быстрее."),
    ("lantern_oil", "Масло для фонарей", 140, "Фонари горят ярче ночью."),
]


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
        for item_key, name, price, _desc in SHOP_ITEMS:
            if item_key != key:
                continue
            if self.coins < price:
                self.notify("Не хватает монет")
                return False
            if key in ("golden_can", "enchanted_rod", "lantern_oil"):
                if getattr(self.upgrades, key):
                    self.notify("Уже куплено")
                    return False
                self.coins -= price
                setattr(self.upgrades, key, True)
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
        for k, v in data.get("upgrades", {}).items():
            if hasattr(self.upgrades, k):
                setattr(self.upgrades, k, bool(v))
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
              livestock=None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = {
        "state": state.to_dict(),
        "farm": farm.to_dict(),
        "livestock": livestock.to_dict() if livestock else {},
        "clock": {"total_time": cycle.total_time},
        "player": {"x": player.pos.x, "y": player.pos.y,
                   "heading": player.heading, "pitch": player.pitch},
    }
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load_game(state: GameState, farm, cycle, player, path: Path = SAVE_PATH,
              livestock=None) -> bool:
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
    cycle.total_time = blob.get("clock", {}).get("total_time", cycle.total_time)
    p = blob.get("player", {})
    if p:
        player.pos.x = p.get("x", player.pos.x)
        player.pos.y = p.get("y", player.pos.y)
        player.pos.z = player.world.height_at(player.pos.x, player.pos.y)
        player.heading = p.get("heading", player.heading)
        player.pitch = p.get("pitch", player.pitch)
    return True
