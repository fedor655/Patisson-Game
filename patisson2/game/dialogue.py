"""What the villagers say, and why they say it now.

Each of the three had a fixed list of lines and read them out in order. Богдан
told you to water your patissons in the middle of a snowstorm, and told you the
same thing again on day forty when the shop was full of gold tools.

A line here belongs to a *topic*, and a topic knows when it applies: crows on
the beds, a ripe harvest waiting, the first frost, midnight, an empty purse.
Every topic that fits contributes its lines to a weighted draw, so an urgent one
usually wins without ever locking the others out — and each villager remembers
the last few things they said so they do not repeat themselves.

The data below is the whole feature; ``choose`` is nine lines long.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

SPRING, SUMMER, AUTUMN, WINTER = 0, 1, 2, 3


@dataclass
class Talk:
    """Everything the villagers are allowed to notice about the world."""

    hour: float = 12.0
    season: int = SPRING
    day: int = 0
    weather: str = "clear"
    sheltering: bool = False
    first_time: bool = False
    coins: int = 0
    crows: int = 0
    ripe: int = 0
    weedy: int = 0
    sick: int = 0
    planted: int = 0
    tilled: int = 0
    fish: int = 0
    quest: str | None = None          # title of the first unfinished quest
    quests_left: int = 0

    @property
    def night(self) -> bool:
        return self.hour >= 22.0 or self.hour < 5.0

    @property
    def morning(self) -> bool:
        return 5.0 <= self.hour < 10.0

    @property
    def evening(self) -> bool:
        return 18.0 <= self.hour < 22.0


@dataclass
class Topic:
    """A reason to say something, and the three villagers' versions of it."""

    name: str
    weight: float
    test: object                       # Talk -> bool
    lines: dict = field(default_factory=dict)

    def applies(self, t: Talk) -> bool:
        return bool(self.test(t))


def _t(fn):
    return fn


TOPICS = [
    # --- things happening right now, loud enough to interrupt -------------
    Topic("crow", 40.0, _t(lambda t: t.crows > 0), {
        "bogdan": ["Ворона! Гони её, пока весь патиссон не склевала.",
                   "Слышишь? Опять эта чёрная над грядками кружит."],
        "marina": ["У тебя ворона на грядке. Я бы поторопилась.",
                   "Птица твой урожай ест — а мне его потом покупать."],
        "pyotr": ["Ворона села. Пугало, значит, никуда не годится.",
                  "Беги, маши руками. Другого способа нет."],
    }),
    Topic("shelter", 26.0, _t(lambda t: t.sheltering), {
        "bogdan": ["Ну и льёт. Грядки хоть поливать не надо.",
                   "Пересидим — и снова за работу.",
                   "В такую погоду только под крышей и сидеть."],
        "marina": ["Под навесом хоть сухо. Товар не мокнет.",
                   "В такую погоду рыба берёт хорошо, между прочим.",
                   "Переждём. Покупателей всё равно нет."],
        "pyotr": ["Куры под крышей, и я с ними.",
                  "Дождь — он земле в радость, а мне в тягость.",
                  "Коровы мокнут, я мокну. Все при деле."],
    }),
    Topic("sick", 20.0, _t(lambda t: t.sick > 0), {
        "bogdan": ["У тебя гниль на грядке. Зола помогает, проверено.",
                   "Больное растение расти перестаёт. Лечи сразу."],
        "marina": ["Гнилое я не куплю, даже не неси.",
                   "Зола есть в лавке. Дешевле, чем потерять грядку."],
        "pyotr": ["Гниль пошла. Сыпь золу, пока соседние не прихватило.",
                  "Земля болеет так же, как скотина. Только не мычит."],
    }),
    Topic("weeds", 16.0, _t(lambda t: t.weedy > 1), {
        "bogdan": ["Сорняки лезут. Дёргай, пока корни мелкие.",
                   "Заросшая грядка родит вполовину. Это не сказки."],
        "marina": ["Грядки у тебя заросли. Видно с прилавка.",
                   "Полол бы ты чаще — и мне товару больше."],
        "pyotr": ["Сорняк — он терпеливый. Дождётся, пока ты устанешь.",
                  "Прополи. Руками, руками, инструмент тут не нужен."],
    }),
    Topic("ripe", 14.0, _t(lambda t: t.ripe > 0), {
        "bogdan": ["Поспело у тебя. Чего стоишь?",
                   "Спелое надо снимать вовремя, иначе перестоит."],
        "marina": ["Урожай поспел — неси, куплю всё.",
                   "У прилавка жду. Спелое не залежится."],
        "pyotr": ["Собирай, пока ворона не собрала.",
                  "Поспело. Так и стоит, тебя дожидается."],
    }),

    # --- the season -------------------------------------------------------
    Topic("spring", 9.0, _t(lambda t: t.season == SPRING), {
        "bogdan": ["Весной сажай что угодно — всё принимается.",
                   "Земля проснулась. Самое время копать грядки."],
        "marina": ["Весной семена дешёвые. Бери с запасом.",
                   "Форель весной берёт с рассвета. Не проспи."],
        "pyotr": ["Весной куры несутся лучше. Проверено годами.",
                  "Трава пошла — коровы довольны, и я с ними."],
    }),
    Topic("summer", 9.0, _t(lambda t: t.season == SUMMER), {
        "bogdan": ["Летом жарко — поливай дважды, не ленись.",
                   "Томат летом идёт хорошо. И осенью тоже."],
        "marina": ["Летом щука выходит под вечер. Запомни час.",
                   "Летом торговля бойкая. Неси что есть."],
        "pyotr": ["Летом коровы дают больше. Трава сочная.",
                  "Жара. Скотине воды побольше, себе тоже."],
    }),
    Topic("autumn", 9.0, _t(lambda t: t.season == AUTUMN), {
        "bogdan": ["Осенью тыква идёт лучше всего. Проверено.",
                   "Осень — последний срок. Что не посадил, то не вырастет."],
        "marina": ["Осенью тыква в цене. Держи это в голове.",
                   "Скоро зима, товар подорожает. Запасайся."],
        "pyotr": ["Осенью пугало держи в порядке. Ворон много.",
                  "Листва летит. Значит, скоро сидеть у печки."],
    }),
    Topic("winter", 9.0, _t(lambda t: t.season == WINTER), {
        "bogdan": ["Зимой ничего не растёт. Отдыхай, заслужил.",
                   "Зимой рыба да котёл — вот и все дела."],
        "marina": ["Зимой семена не бери, пропадут. Бери снасти.",
                   "Зима — время считать деньги, а не сеять."],
        "pyotr": ["Зимой скотину кормить чаще. Сама себе травы не найдёт.",
                  "Мороз. Куры сидят, коровы стоят, я хожу."],
    }),

    # --- the hour ---------------------------------------------------------
    Topic("morning", 7.0, _t(lambda t: t.morning), {
        "bogdan": ["Доброе утро. Роса ещё не сошла — самое время полить.",
                   "Рано встал — полдня выиграл."],
        "marina": ["Утро. Лавка открыта, заходи.",
                   "Утром форель берёт лучше всего. Иди к пруду."],
        "pyotr": ["Куры уже накормлены. А ты завтракал?",
                  "С утра дела, к вечеру покой. Так заведено."],
    }),
    Topic("evening", 7.0, _t(lambda t: t.evening), {
        "bogdan": ["Вечер. Полей на ночь — к утру примется.",
                   "День прошёл, а грядки на месте. Хорошо."],
        "marina": ["Закрываюсь скоро. Успевай.",
                   "Вечером щука выходит. Самое время."],
        "pyotr": ["Скотина в стойле, я на воздухе. Хорошо.",
                  "Вечером хорошо думается. И курится."],
    }),
    Topic("night", 8.0, _t(lambda t: t.night), {
        "bogdan": ["Ты чего не спишь? Земля и утром никуда не денется.",
                   "Ночью на грядках делать нечего. Иди ложись."],
        "marina": ["Ночью на ферме красиво. И тихо.",
                   "Сом ночной. Если не спится — бери удочку."],
        "pyotr": ["Ночь. Даже куры угомонились.",
                  "Спать надо. Земля не убежит."],
    }),

    # --- how it's going ---------------------------------------------------
    # Nothing grows in winter, so nobody nags you about empty beds then.
    Topic("first_field", 12.0,
          _t(lambda t: t.tilled == 0 and t.season != WINTER), {
        "bogdan": ["Возьми мотыгу и вскопай грядку. С этого всё и начинается.",
                   "Пока земля не копана, и говорить не о чем."],
        "marina": ["Семена у меня есть, а грядки у тебя нет. Непорядок.",
                   "Вскопай хоть одну. Потом придёшь за семенами."],
        "pyotr": ["Земля сама себя не вскопает.",
                  "Мотыга в руках — уже полдела."],
    }),
    Topic("empty_field", 10.0,
          _t(lambda t: t.tilled > 0 and t.planted == 0 and t.season != WINTER), {
        "bogdan": ["Грядки пустые стоят. Сажай, чего ждёшь.",
                   "Вскопал — теперь сей. Иначе зря копал."],
        "marina": ["Семена в лавке. Пустая грядка денег не приносит.",
                   "Купи семян. У меня как раз свежие."],
        "pyotr": ["Пустая земля — она сорняком зарастёт, и всё.",
                  "Сажай. Хоть пшеницу, она неприхотливая."],
    }),
    Topic("broke", 8.0, _t(lambda t: t.coins < 25 and t.day > 0), {
        "bogdan": ["Денег нет — продай урожай. Марина берёт всё.",
                   "Пустой кошелёк — не беда. Беда, когда грядки пустые."],
        "marina": ["Совсем на мели? Неси рыбу, я не привередливая.",
                   "В долг не даю. Но покупаю честно."],
        "pyotr": ["Яйца собери да продай. Куры на что?",
                  "Молоко всегда в цене. Хоть какие-то деньги."],
    }),
    Topic("rich", 8.0, _t(lambda t: t.coins >= 1200), {
        "bogdan": ["Разбогател! Купи золотую лейку, не жадничай.",
                   "С такими деньгами можно и инструмент сменить."],
        "marina": ["О, у тебя завелись деньги. Заходи, поговорим.",
                   "Богатому и семена слаще. Бери лучшие."],
        "pyotr": ["Денег много — а грядки те же. Смешно.",
                  "Купи уже нормальную мотыгу, стыдно смотреть."],
    }),
    Topic("no_fish", 6.0, _t(lambda t: t.fish == 0 and t.day > 0), {
        "bogdan": ["На пруду не был? Зря. Там половина дохода.",
                   "Удочка в сумке лежит без дела."],
        "marina": ["Рыбу я покупаю дороже овощей. Намёк понял?",
                   "Возьми удочку. Плотва клюёт в любое время."],
        "pyotr": ["Рыбалка — единственный отдых, который кормит.",
                  "Сходи к пруду. Хоть сапог вытащишь."],
    }),
    Topic("angler", 6.0, _t(lambda t: t.fish >= 20), {
        "bogdan": ["Ты весь пруд выловишь такими темпами.",
                   "Рыбак из тебя вышел лучше, чем огородник."],
        "marina": ["Столько рыбы я и за месяц не продам. Молодец.",
                   "Щуку поймал? А золотую рыбку видел?"],
        "pyotr": ["Рыбы у тебя больше, чем у меня кур.",
                  "В пруду хоть что-то осталось?"],
    }),
    Topic("quest", 7.0, _t(lambda t: t.quest is not None), {
        "bogdan": ["Слышал, ты взялся за «{quest}». Дело хорошее.",
                   "Не бросай «{quest}» на полпути."],
        "marina": ["«{quest}» — доведи до конца, за это платят.",
                   "Про «{quest}» не забудь. В журнале записано."],
        "pyotr": ["«{quest}»… Ну-ну. Посмотрим.",
                  "Взялся за «{quest}» — делай."],
    }),
    Topic("all_done", 10.0, _t(lambda t: t.quests_left == 0 and t.day > 0), {
        "bogdan": ["Все задания переделал. Теперь просто живи.",
                   "Ферма на тебе держится. Спасибо."],
        "marina": ["Ты всё выполнил. Даже неловко — просить больше нечего.",
                   "Лучший клиент за всю мою торговлю."],
        "pyotr": ["Всё сделал. Редкий случай.",
                  "Ну, теперь можно и покурить спокойно."],
    }),

    # --- nothing in particular --------------------------------------------
    Topic("idle", 5.0, _t(lambda _t_: True), {
        "bogdan": ["Вот и дождались! Ферма снова живая.",
                   "Патиссон любит воду. Не забывай поливать.",
                   "Колодец у дома — набирай сколько нужно.",
                   "Земля любит руки, а не разговоры.",
                   "В игре могут быть баги. Веселись!"],
        "marina": ["Свежая рыба! Ну, почти свежая.",
                   "Продавай урожай у прилавка — я хорошо плачу.",
                   "Золотая лейка дорогая, но воду носить перестанешь.",
                   "Удочка получше — рыба покрупнее. Это не реклама.",
                   "Зайди в лавку, там всегда что-нибудь новое."],
        "pyotr": ["Куры опять разбежались. Как всегда.",
                  "Дождь будет — грядки польются сами.",
                  "Земля тут добрая, если за ней ходить.",
                  "Пугало проверь. Оно от дождя раскисает.",
                  "Корову покормишь — молоко будет. Простая арифметика."],
    }),
]

# Said once, the very first time you talk to each of them.
GREETINGS = {
    "bogdan": "Ты, значит, новый хозяин? Богдан. Спрашивай, если что.",
    "marina": "Марина. Держу лавку. Покупаю всё, что растёт и плавает.",
    "pyotr": "Пётр. Скотина на мне. С тобой пока незнаком.",
}


def choose(key: str, t: Talk, rng: random.Random, recent=()) -> str:
    """Pick a line for one villager: weighted across every topic that fits."""
    if t.first_time and key in GREETINGS:
        return GREETINGS[key]
    pool = []
    for topic in TOPICS:
        lines = topic.lines.get(key)
        if not lines or not topic.applies(t):
            continue
        fresh = [ln for ln in lines if ln not in recent]
        weight = topic.weight
        if not fresh:
            # Said everything this topic has lately: let it through, but
            # quietly, so a loud topic cannot repeat itself forever.
            fresh, weight = list(lines), topic.weight * 0.2
        share = weight / len(fresh)
        pool.extend((share, ln) for ln in fresh)
    if not pool:
        return GREETINGS.get(key, "…")
    total = sum(w for w, _ln in pool)
    roll = rng.uniform(0.0, total)
    for weight, line in pool:
        roll -= weight
        if roll <= 0.0:
            return line.replace("{quest}", t.quest or "")
    return pool[-1][1].replace("{quest}", t.quest or "")
