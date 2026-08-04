"""The hearth: turn raw produce into dishes worth far more than their parts.

Cooking is the farm's main money multiplier — selling a pumpkin pays 88, but a
pie made from one is worth 320. Dishes also restore stamina when eaten.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .farming import CROPS
from .livestock import PRODUCT_NAMES, PRODUCT_PRICE

POT_POSITION = (13.4, -8.4)


@dataclass(frozen=True)
class Recipe:
    key: str
    name: str
    inputs: dict           # item key -> count
    sell_price: int
    stamina: float
    note: str = ""


RECIPES: tuple[Recipe, ...] = (
    Recipe("bread", "Хлеб", {"wheat": 3}, 52, 22.0,
           "Простой, но всегда в цене."),
    Recipe("omelette", "Омлет", {"egg": 2, "milk": 1}, 78, 34.0,
           "Нужны куры и корова."),
    Recipe("fish_soup", "Уха", {"fish": 2, "carrot": 1}, 96, 42.0,
           "Из пруда прямо в котёл."),
    Recipe("caviar", "Патиссоновая икра", {"patisson": 2, "tomato": 1}, 178, 30.0,
           "Фирменное блюдо фермы."),
    Recipe("pie", "Тыквенный пирог", {"pumpkin": 1, "wheat": 2, "egg": 1, "milk": 1},
           320, 60.0, "Осенний деликатес."),
)

RECIPE_BY_KEY = {r.key: r for r in RECIPES}

# Everything the shop and the stall need to know how to price and name.
DISH_PRICE = {r.key: r.sell_price for r in RECIPES}
DISH_NAMES = {r.key: r.name for r in RECIPES}


def item_name(key: str) -> str:
    if key in CROPS:
        return CROPS[key].name
    if key in PRODUCT_NAMES:
        return PRODUCT_NAMES[key]
    if key in DISH_NAMES:
        return DISH_NAMES[key]
    if key == "fish":
        return "Рыба"
    return key


def item_price(key: str) -> int:
    if key in CROPS:
        return CROPS[key].sell_price
    if key in PRODUCT_PRICE:
        return PRODUCT_PRICE[key]
    return DISH_PRICE.get(key, 0)


class Kitchen:
    """Recipe selection and the cook/eat actions."""

    def __init__(self, state):
        self.state = state
        self.index = 0

    @property
    def recipe(self) -> Recipe:
        return RECIPES[self.index]

    def move(self, delta: int) -> None:
        self.index = (self.index + delta) % len(RECIPES)

    def missing(self, recipe: Recipe | None = None) -> dict:
        """Ingredients still needed, item key -> shortfall."""
        recipe = recipe or self.recipe
        short = {}
        for key, need in recipe.inputs.items():
            have = self.state.fish if key == "fish" else self.state.count(key)
            if have < need:
                short[key] = need - have
        return short

    def can_cook(self, recipe: Recipe | None = None) -> bool:
        return not self.missing(recipe)

    def cook(self) -> Recipe | None:
        recipe = self.recipe
        if not self.can_cook(recipe):
            return None
        for key, need in recipe.inputs.items():
            if key == "fish":
                self.state.fish -= need
            else:
                self.state.take(key, need)
        self.state.give(recipe.key, 1)
        self.state.cooked[recipe.key] = self.state.cooked.get(recipe.key, 0) + 1
        return recipe

    def eat(self, player) -> Recipe | None:
        recipe = self.recipe
        if not self.state.take(recipe.key, 1):
            return None
        player.stamina = min(player.cfg.stamina_max,
                             player.stamina + recipe.stamina)
        return recipe
