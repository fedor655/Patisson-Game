"""Crops, plots and growth.

A plot tracks water, nutrients and health. Water is what keeps a plant alive —
let a bed dry out and it withers — while food only decides how fast it grows.
Rain waters everything for free, and each crop only thrives in its own seasons.
"""

from __future__ import annotations

import random

from dataclasses import dataclass

from .view import Node, Vec3, place



@dataclass(frozen=True)
class Crop:
    key: str
    name: str
    stages: tuple            # ((model, scale), ...) low -> ripe
    grow_days: float         # rate parameter, NOT an observable time:
                             # only a bed held at full water and full food
                             # ripens this fast. Use days_to_ripe().
    seed_price: int
    sell_price: int
    seasons: tuple           # season indices where it grows at full speed
    thirst: float = 1.0      # water use multiplier
    yield_count: int = 1


# The prices are not free parameters. Four of the five crops used to be
# beaten by another crop on profit AND speed AND season coverage all at once
# -- including the patisson the game is named after, which wheat outgrew
# twice as fast for half again the money. Nothing was worth planting but
# tomatoes and wheat.
#
# The rule now: the longer a bed is tied up and the fewer seasons a crop
# will take, the better it has to pay. That leaves every crop a reason to
# exist -- wheat is the fast cheap staple, the pumpkin is the autumn
# jackpot, and each step up the ladder costs patience or a season.
# `no_crop_is_dominated` in the smoke test holds this to it.
CROPS: dict[str, Crop] = {
    "patisson": Crop(
        "patisson", "Патиссон",
        (("patisson_0", 1.0), ("patisson_1", 1.0), ("patisson_2", 1.0), ("patisson_3", 1.0)),
        grow_days=2.5, seed_price=10, sell_price=52, seasons=(0, 1, 2), yield_count=1),
    "carrot": Crop(
        "carrot", "Морковь",
        (("patisson_0", 0.9), ("carrot", 0.55), ("carrot", 1.0)),
        grow_days=1.5, seed_price=4, sell_price=13, seasons=(0, 1, 2), thirst=0.85,
        yield_count=2),
    "tomato": Crop(
        "tomato", "Томат",
        (("patisson_0", 1.0), ("tomato", 0.5), ("tomato", 1.0)),
        grow_days=2.0, seed_price=8, sell_price=22, seasons=(1, 2), thirst=1.25,
        yield_count=2),
    "wheat": Crop(
        "wheat", "Пшеница",
        (("patisson_0", 0.8), ("wheat", 0.55), ("wheat", 1.0)),
        grow_days=1.2, seed_price=3, sell_price=6, seasons=(0, 1, 2), thirst=0.7,
        yield_count=3),
    # Единственное, что вызревает зимой. Числа выведены, а не
    # выдуманы: 1.6 даёт 3.1 дня до спелости, то есть два урожая
    # укладываются в семидневную зиму; 9 монет за корень при двух
    # корнях с грядки — это 4.6 монеты в день против 6.6 у самой
    # слабой летней культуры. Зима худая, но не пустая.
    "turnip": Crop(
        "turnip", "Репа",
        (("patisson_0", 0.7), ("turnip", 0.55), ("turnip", 1.0)),
        grow_days=1.6, seed_price=4, sell_price=9, seasons=(3,),
        thirst=0.7, yield_count=2),
    "pumpkin": Crop(
        "pumpkin", "Тыква",
        (("patisson_0", 1.1), ("pumpkin", 0.42), ("pumpkin", 0.72), ("pumpkin", 1.0)),
        grow_days=3.5, seed_price=16, sell_price=88, seasons=(2,), thirst=1.4),
}

CROP_ORDER = ("patisson", "carrot", "tomato", "wheat", "pumpkin",
               "turnip")

# What one action gives a bed, and what a bed loses on its own.
WATER_AMOUNT = 0.55         # one pour from the can
FEED_AMOUNT = 0.6           # one sack of fertiliser
PLANT_WATER = 0.35          # a seed goes into damp ground
PLANT_FOOD = 0.3
FOOD_DECAY = 0.85           # per in-game day
WATER_DECAY = 1.35          # per day, before the crop's own thirst
TEND_WATER_AT = 0.5         # a diligent player tops the can up here
TEND_FOOD_AT = 0.6          # ... and keeps the bonus fruit within reach

# --- weeds ------------------------------------------------------------------
# Hoeing is meant to be a daily job, and the thresholds follow from that
# rather than the other way round. They used to be three bare numbers —
# 0.22, 0.35, 0.70 — which in play meant the tuft showed after nine game
# hours, growth suffered after thirteen, and a bed left a day and a bit
# was drinking itself dry: two rounds of the hoe a day across twenty-four
# beds to avoid any penalty at all.
#
# What a designer actually decides is the grace period. The levels are
# integrated from the same weed formula the farm runs, on a bed that is
# watered and not fertilised — the way a bed is normally kept.
WEED_GRACE_VISIBLE = 0.5    # half a day and the tuft shows
WEED_GRACE_SLOW = 1.0       # a day without the hoe and growth suffers
WEED_GRACE_THIRST = 1.5     # a day and a half and the weeds drink the bed


def weed_rate(water: float, food: float) -> float:
    """Weeds gained per in-game day. Damp, well-fed ground grows more."""
    return 0.95 * (0.55 + 0.45 * water) * (0.7 + 0.3 * food)


def _weeds_after(days: float, step: float = 1.0 / 240.0) -> float:
    """How overgrown a normally-kept bed is after `days` of no hoeing.

    No thirst multiplier here, and none is needed: it only applies above
    WEED_THIRST, which is defined as the level at the longest grace
    period, so it cannot have kicked in before then.
    """
    water, food, weeds, t = PLANT_WATER, PLANT_FOOD, 0.0, 0.0
    while t < days:
        weeds = min(1.0, weeds + step * weed_rate(water, food))
        water = max(0.0, water - step * WATER_DECAY)
        food = max(0.0, food - step * FOOD_DECAY)
        if water < TEND_WATER_AT:
            water = min(1.0, water + WATER_AMOUNT)
        t += step
    return round(weeds, 2)


WEED_START = _weeds_after(WEED_GRACE_VISIBLE)    # 0.31 — visible from here
WEED_SLOW = _weeds_after(WEED_GRACE_SLOW)        # 0.60 — growth suffers
WEED_THIRST = _weeds_after(WEED_GRACE_THIRST)    # 0.90 — and they drink

# --- blight -----------------------------------------------------------------
# Rot takes hold in ground that is damp *and* neglected or overfed. Rain
# alone used to be enough, and rain fills every bed to the brim in
# seconds: there was nothing the player could do about it, so blight was
# weather damage with an ash bill attached rather than a consequence of
# anything. Now the damp is the trigger and the player's own bed is the
# cause — let the weeds past the point where they already cost you
# growth, or keep the soil rich, and it rots.
BLIGHT_SOGGY = 0.82         # wet enough for it
BLIGHT_RICH = 0.75          # fat enough for it
BLIGHT_DAILY_CHANCE = 0.55  # per in-game day, per susceptible plot

# One sack of fertiliser just before picking buys the bonus fruit: the
# extra is granted when the bed is this healthy and this well fed at the
# moment of harvest. Topping the bed up all season loses money — the
# almanac and Богдан both say so, quoting these numbers.
BONUS_HEALTH = 0.92
BONUS_FOOD = 0.6


def growth_rate(crop: Crop, water: float, food: float, weeds: float,
                in_season: bool) -> float:
    """Progress per in-game day for a bed in this condition.

    One source of truth, because two places need this number: the
    simulation that grows the crop, and the almanac that tells the player
    how long it will take.
    """
    rate = 1.0 / crop.grow_days
    if not in_season:
        rate *= 0.28          # out of season: slow, not impossible
    rate *= 0.75 + 0.25 * water
    # Starved: a little over half speed. Fed: full speed and the extra
    # fruit at harvest.
    rate *= 0.55 + 0.45 * food
    if weeds >= WEED_SLOW:
        rate *= 1.0 - 0.55 * (weeds - WEED_SLOW) / (1.0 - WEED_SLOW)
    return rate


def days_to_ripe(crop: Crop, *, fertilised: bool = False,
                 in_season: bool = True) -> float:
    """In-game days from seed to ripe for a player who tends the bed.

    Integrated from `growth_rate` rather than read off `crop.grow_days`.
    That field is the rate parameter, not a time anybody can observe: it
    is only reached by a bed held at full food and full water, so the
    almanac's "растёт 2 дн." described a patisson nobody has ever grown —
    a watered but unfertilised one takes 4.8.
    """
    water, food = PLANT_WATER, PLANT_FOOD
    progress, days, step = 0.0, 0.0, 1.0 / 240.0
    while progress < 1.0 and days < 90.0:
        progress += step * growth_rate(crop, water, food, 0.0, in_season)
        days += step
        water = max(0.0, water - step * WATER_DECAY * crop.thirst)
        food = max(0.0, food - step * FOOD_DECAY)
        if water < TEND_WATER_AT:
            water = min(1.0, water + WATER_AMOUNT)
        if fertilised and food < TEND_FOOD_AT:
            food = min(1.0, food + FEED_AMOUNT)
    return days


@dataclass
class Plot:
    x: float
    y: float
    z: float
    crop: str | None = None
    progress: float = 0.0        # 0..1
    water: float = 0.0           # 0..1
    food: float = 0.0            # 0..1
    health: float = 1.0
    tilled: bool = False
    node: Node | None = None
    stage: int = -1
    weeds: float = 0.0           # 0..1, choke the crop if left alone
    blight: float = 0.0          # 0..1, halts growth until treated
    weed_node: Node | None = None
    bed_node: Node | None = None
    _wither_warned: bool = False
    _blight_warned: bool = False

    @property
    def ripe(self) -> bool:
        return self.crop is not None and self.progress >= 1.0

    @property
    def weedy(self) -> bool:
        return self.weeds >= 0.30

    @property
    def sick(self) -> bool:
        return self.blight >= 0.05

    @property
    def pos(self) -> Vec3:
        return Vec3(self.x, self.y, self.z)


class Farm:
    """All the plots, their state, and the plant models standing in them."""

    def __init__(self, base, world, props, day_length: float):
        self.base = base
        self.world = world
        self.props = props
        self.day_length = day_length
        self.root = world.root.attachNewNode("crops")
        props.pipeline.apply_scene_shader(self.root, wind=0.35, wind_pivot=0.02)
        self.plots: list[Plot] = []
        self.harvest_log: dict[str, int] = {}
        self.rng = random.Random(0xC0FFEE)

    # -------------------------------------------------------------- plots

    def add_plot(self, x: float, y: float, tilled: bool = True) -> Plot:
        z = self.world.height_at(x, y)
        plot = Plot(x, y, z, tilled=tilled)
        self.plots.append(plot)
        if tilled:
            # The mask still darkens the ground and keeps grass out, but the
            # bed itself is geometry now: the mask alone (3.5 px/m) drew a
            # blurry smudge where the player expected tilled soil.
            self.world.mask.paint(x, y, 0.52, 0)
            h = (hash((round(x, 2), round(y, 2))) * 7) % 4 * 90.0
            plot.bed_node = place(self.root, "plot_bed",
                                  (x, y, z - 0.035), h, 1.0)
        return plot

    def nearest(self, pos: Vec3, radius: float = 2.0) -> Plot | None:
        best, best_d = None, radius * radius
        for p in self.plots:
            d = (p.x - pos.x) ** 2 + (p.y - pos.y) ** 2
            if d < best_d:
                best, best_d = p, d
        return best

    def till(self, x: float, y: float) -> Plot | None:
        if not self.world.can_till(x, y):
            return None
        existing = self.nearest(Vec3(x, y, 0), 0.9)
        if existing is not None:
            return None
        return self.add_plot(x, y)

    # ------------------------------------------------------------- actions

    def plant(self, plot: Plot, crop_key: str) -> bool:
        if plot.crop is not None or not plot.tilled:
            return False
        plot.crop = crop_key
        plot.progress = 0.0
        plot.health = 1.0
        plot.water = max(plot.water, PLANT_WATER)
        plot.food = max(plot.food, PLANT_FOOD)
        plot.stage = -1
        plot._wither_warned = False
        self._refresh_model(plot)
        return True

    def water_plot(self, plot: Plot, amount: float = WATER_AMOUNT) -> bool:
        if plot.crop is None:
            return False
        if plot.water >= 0.98:
            return False
        plot.water = min(1.0, plot.water + amount)
        return True

    def feed_plot(self, plot: Plot, amount: float = FEED_AMOUNT) -> bool:
        if plot.crop is None or plot.food >= 0.98:
            return False
        plot.food = min(1.0, plot.food + amount)
        return True

    def _refresh_weeds(self, plot: Plot) -> None:
        """Show a tuft once the weeds are worth noticing."""
        want = plot.weeds >= WEED_START
        if want and plot.weed_node is None:
            plot.weed_node = place(self.props.dynamic, "weeds",
                                   (plot.x, plot.y, plot.z + 0.06),
                                   (plot.x * 37 + plot.y * 11) % 360, 1.0)
        elif not want and plot.weed_node is not None:
            plot.weed_node.removeNode()
            plot.weed_node = None
        if plot.weed_node is not None:
            scale = 0.55 + 0.75 * plot.weeds
            plot.weed_node.setScale(scale)

    def weed(self, plot: Plot) -> bool:
        """Hoe the weeds out of a bed."""
        if plot.weeds < 0.05:
            return False
        plot.weeds = 0.0
        self._refresh_weeds(plot)
        return True

    def cure(self, plot: Plot) -> bool:
        if not plot.sick:
            return False
        plot.blight = 0.0
        plot._blight_warned = False
        return True

    def harvest(self, plot: Plot, basket_bonus: int = 0) -> tuple[str, int] | None:
        if not plot.ripe:
            return None
        crop = CROPS[plot.crop]
        bonus = 1 if plot.health > BONUS_HEALTH and plot.food > BONUS_FOOD else 0
        count = crop.yield_count + bonus + basket_bonus
        self.harvest_log[crop.key] = self.harvest_log.get(crop.key, 0) + count
        plot.crop = None
        plot.progress = 0.0
        plot.stage = -1
        plot.food = max(0.0, plot.food - 0.45)
        self._clear_model(plot)
        return crop.key, count

    def clear(self, plot: Plot) -> None:
        plot.crop = None
        plot.progress = 0.0
        plot.stage = -1
        plot.blight = 0.0
        plot._blight_warned = False
        self._clear_model(plot)

    # -------------------------------------------------------------- update

    def update(self, dt: float, season: int, raining: bool) -> list[str]:
        """Advance every plot. Returns notification strings."""
        events: list[str] = []
        day_frac = dt / self.day_length
        for plot in self.plots:
            if raining:
                plot.water = min(1.0, plot.water + dt * 0.06)
            if plot.crop is None:
                plot.water = max(0.0, plot.water - day_frac * 0.5)
                continue

            crop = CROPS[plot.crop]

            # Одна формула на всех: по ней же выведены пороги.
            rate = weed_rate(plot.water, plot.food)
            if season == 3:
                rate *= 0.25                 # little grows in winter
            plot.weeds = min(1.0, plot.weeds + day_frac * rate)

            thirst = WATER_DECAY * crop.thirst
            if plot.weeds >= WEED_THIRST:
                thirst *= 1.7                # the weeds are drinking it too
            plot.water = max(0.0, plot.water - day_frac * thirst)
            plot.food = max(0.0, plot.food - day_frac * FOOD_DECAY)

            # Blight takes hold in sodden beds, and spreads once it has.
            if plot.blight <= 0.0:
                soggy = (plot.water >= BLIGHT_SOGGY
                         and (plot.weeds >= WEED_SLOW
                              or plot.food > BLIGHT_RICH))
                if soggy and self.rng.random() < day_frac * BLIGHT_DAILY_CHANCE:
                    plot.blight = 0.35
            else:
                plot.blight = min(1.0, plot.blight + day_frac * 0.55)
                plot.health = max(0.0, plot.health - day_frac * 0.9)
                if not plot._blight_warned:
                    plot._blight_warned = True
                    events.append(f"{crop.name} поразила гниль — нужна зола.")

            # Water keeps a plant alive; food only decides how fast it grows.
            # Food used to gate survival as well, and since planting gives 0.3
            # against a decay of 0.85 a day, every bed starved after eight
            # hours: watered faithfully and never fertilised, every crop
            # withered to nothing and none of them ever ripened. Fertiliser is
            # sold as "питание для растения", not as life support.
            healthy = plot.water > 0.04
            if healthy and not plot.sick:
                plot.health = min(1.0, plot.health + day_frac * 1.2)
                rate = growth_rate(crop, plot.water, plot.food, plot.weeds,
                                   season in crop.seasons)
                plot.progress = min(1.0, plot.progress + day_frac * rate)
            else:
                plot.health = max(0.0, plot.health - day_frac * 1.6)
                if plot.health < 0.35 and not plot._wither_warned:
                    plot._wither_warned = True
                    events.append(f"{crop.name} вянет — нужна вода!")
                if plot.health <= 0.0:
                    events.append(f"{crop.name} погиб.")
                    self.clear(plot)
                    continue

            self._refresh_weeds(plot)
            stage = self._stage_for(crop, plot.progress)
            if stage != plot.stage:
                if plot.stage >= 0 and stage == len(crop.stages) - 1:
                    events.append(f"{crop.name} созрел!")
                self._refresh_model(plot)
        return events

    @staticmethod
    def _stage_for(crop: Crop, progress: float) -> int:
        n = len(crop.stages)
        if progress >= 1.0:
            return n - 1
        return min(n - 1, int(progress * (n - 1) + 1e-6))

    def _clear_model(self, plot: Plot):
        if plot.node is not None:
            plot.node.removeNode()
            plot.node = None

    def _refresh_model(self, plot: Plot):
        self._clear_model(plot)
        if plot.crop is None:
            return
        crop = CROPS[plot.crop]
        stage = self._stage_for(crop, plot.progress)
        plot.stage = stage
        model, scale = crop.stages[stage]
        # Wilting plants shrink and droop a little.
        scale *= 0.65 + 0.35 * plot.health
        h = (hash((round(plot.x, 2), round(plot.y, 2))) % 360)
        # On the bed's soil, not buried under it: the slab top sits ~5 cm up.
        plot.node = place(self.root, model, (plot.x, plot.y, plot.z + 0.05), h, scale)
        if plot.health < 0.55:
            plot.node.setColorScale(0.72 + 0.28 * plot.health,
                                    0.55 + 0.45 * plot.health,
                                    0.42 + 0.35 * plot.health, 1.0)

    # ---------------------------------------------------------------- save

    def to_dict(self) -> dict:
        return {
            "plots": [
                {"x": p.x, "y": p.y, "crop": p.crop, "progress": p.progress,
                 "water": p.water, "food": p.food, "health": p.health,
                 "tilled": p.tilled, "weeds": p.weeds, "blight": p.blight}
                for p in self.plots
            ],
            "harvested": self.harvest_log,
        }

    def from_dict(self, data: dict):
        from .state import as_dict, as_float, as_int, as_list

        data = as_dict(data)
        for plot in self.plots:
            self._clear_model(plot)
            if plot.weed_node is not None:
                plot.weed_node.removeNode()
                plot.weed_node = None
        self.plots.clear()
        for d in as_list(data.get("plots")):
            d = as_dict(d)
            if "x" not in d or "y" not in d:
                continue
            plot = self.add_plot(as_float(d["x"]), as_float(d["y"]),
                                 bool(d.get("tilled", True)))
            # A crop this build does not have — an older save, or an edited
            # one — would otherwise take the loader down looking for its model.
            crop = d.get("crop")
            plot.crop = crop if crop in CROPS else None
            plot.progress = min(1.0, max(0.0, as_float(d.get("progress"))))
            plot.water = min(1.0, max(0.0, as_float(d.get("water"))))
            plot.food = min(1.0, max(0.0, as_float(d.get("food"))))
            plot.health = min(1.0, max(0.0, as_float(d.get("health"), 1.0)))
            plot.weeds = min(1.0, max(0.0, as_float(d.get("weeds"))))
            plot.blight = min(1.0, max(0.0, as_float(d.get("blight"))))
            self._refresh_weeds(plot)
            if plot.crop:
                self._refresh_model(plot)
        self.harvest_log = {str(k): as_int(v)
                            for k, v in as_dict(data.get("harvested")).items()}
