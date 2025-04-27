import uuid


base_cards = [
    # base
    *[{"id": "onion", "type": "regular", "name": "Цибуля", "cost": 1, "points": 1} for _ in range(9)],
    *[{"id": "potato", "type": "regular", "name": "Картопля", "cost": 1, "points": 0} for _ in range(9)],
    *[{"id": "beet", "type": "regular", "name": "Буряк", "cost": 2, "points": 1} for _ in range(7)],
    *[{"id": "cabbage", "type": "regular", "name": "Капуста білоголова", "cost": 1, "points": 1} for _ in range(7)],
    *[{"id": "carrot", "type": "regular", "name": "Морква", "cost": 2, "points": 0} for _ in range(9)],
    *[{"id": "celery_root", "type": "regular", "name": "Корінь селери", "cost": 2, "points": 1} for _ in range(7)],
    *[{"id": "tomato_paste", "type": "regular", "name": "Томатна паста", "cost": 2, "points": 1} for _ in range(6)],
    *[{"id": "sweet_pepper", "type": "regular", "name": "Перець солодкий", "cost": 2, "points": 2} for _ in range(6)],
    *[{"id": "fresh_tomato", "type": "regular", "name": "Свіжий томат", "cost": 2, "points": 2} for _ in range(6)],
    *[{"id": "pork", "type": "regular", "name": "Свинина", "cost": 2, "points": 1} for _ in range(6)],

    # rare
    *[{"id": "beef", "type": "rare", "name": "Яловичина", "cost": 3, "points": 2} for _ in range(4)],
    *[{"id": "beans", "type": "rare", "name": "Квасоля", "cost": 3, "points": 2} for _ in range(3)],
    *[{"id": "eggs", "type": "rare", "name": "Яйця", "cost": 4, "points": 3} for _ in range(4)],
    *[{"id": "mushroom", "type": "rare", "name": "Гриби", "cost": 3, "points": 2} for _ in range(3)],
    *[{"id": "white_beet", "type": "rare", "name": "Буряк білий", "cost": 5, "points": 4} for _ in range(3)],
    *[{"id": "lamb", "type": "rare", "name": "Баранина на кістці", "cost": 6, "points": 4} for _ in range(2)],
    *[{"id": "prunes", "type": "rare", "name": "Чорнослив", "cost": 5, "points": 3} for _ in range(3)],
    *[{"id": "sorrel", "type": "rare", "name": "Щавель", "cost": 5, "points": 4} for _ in range(2)],
    *[{"id": "chicken", "type": "rare", "name": "Курятина", "cost": 5, "points": 4} for _ in range(2)],
    *[{"id": "fish", "type": "rare", "name": "Риба", "cost": 5, "points": 3} for _ in range(3)],
    *[{"id": "eggplant", "type": "rare", "name": "Баклажан", "cost": 4, "points": 2} for _ in range(2)],
    *[{"id": "flour", "type": "rare", "name": "Борошно", "cost": 3, "points": 2} for _ in range(4)],
    *[{"id": "beet_kvass", "type": "rare", "name": "Буряковий квас", "cost": 6, "points": 3} for _ in range(3)],
    *[{"id": "sauerkraut", "type": "rare", "name": "Квашена капуста", "cost": 3, "points": 2} for _ in range(3)],
    *[{"id": "sauerkraut_tomato", "type": "rare", "name": "Квашений томат", "cost": 6, "points": 3} for _ in range(3)],
    *[{"id": "smoked_pear", "type": "rare", "name": "Копчена груша", "cost": 6, "points": 4} for _ in range(3)],
    *[{"id": "apple", "type": "rare", "name": "Яблуко", "cost": 6, "points": 4} for _ in range(2)],
    *[{"id": "home_sauseges", "type": "rare", "name": "Домашня ковбаса", "cost": 6, "points": 4} for _ in range(2)],
    *[{"id": "honey", "type": "rare", "name": "Мед", "cost": 6, "points": 4} for _ in range(2)],

    # extra
    *[{"id": "salt", "type": "extra", "name": "Сіль", "cost": 1, "points": 2} for _ in range(5)],
    *[{"id": "garlic", "type": "extra", "name": "Часник", "cost": 5, "points": 4} for _ in range(3)],
    *[{"id": "vinnik_lard", "type": "extra", "name": "Вінницьке сало", "cost": 6, "points": 0, "effect_description": "Замінює будь-який інгредієнт з рецепту"} for _ in range(2)],
    *[{"id": "rye_bread", "type": "extra", "name": "Житній хлібчик", "cost": 6, "points": 5} for _ in range(2)],
    *[{"id": "bay_leaf", "type": "extra", "name": "Лавровий лист", "cost": 4, "points": 3} for _ in range(4)],
    *[{"id": "vitamin_bunch", "type": "extra", "name": "Вітамінний пучок", "cost": 2, "points": 2} for _ in range(6)],

    # special
    *[{"id": "chili_pepper", "type": "special", "name": "Перець вогник", "cost": 4, "effect": "steal_or_discard", "effect_description": "Перемістіть у свій борщ або скиньте будь-який інгредієнт з борщу іншого гравця."} for _ in range(8)],
    *[{"id": "black_pepper", "type": "special", "name": "Чорний перець", "cost": 3, "effect": "discard_or_take", "effect_description": "Скиньте 1 інгредієнт з борщу кожного суперника АБО заеріть по 1 випадковій карті з руки кожного суперника."} for _ in range(3)],
    *[{"id": "sour_cream", "type": "special", "name": "Сметана", "cost": 4, "effect": "defense", "effect_description": "Скиньте, щоб захиститись від ефектів карт «Чорний перець» або «Перець вогник»."} for _ in range(6)],
    *[{"id": "ginger", "type": "special", "name": "Імбир", "cost": 3, "effect": "take_market", "effect_description": "Візьміть на руку 2 будь-які інгредієнти з ринку і поповніть ринок."} for _ in range(3)],
    *[{"id": "cinnamon", "type": "special", "name": "Кориця", "cost": 5, "effect": "take_discard", "effect_description": "Перегляньте скид і візьміть на руку 1 карту інгредієнта."} for _ in range(3)],
    *[{"id": "olive_oil", "type": "special", "name": "Оливкова олія", "cost": 3, "effect": "look_top_5", "effect_description": "Перегляньте 5 верхніх карт у колоді інгредієнтів. Візьміть на руку 2 карти, інші 3 поверніть у колоду."} for _ in range(5)],
    *[{"id": "paprika", "type": "special", "name": "Паприка", "cost": 4, "effect": "refresh_market", "effect_description": "Оновіть ринок. Після цього можете виконати обмін."} for _ in range(10)],
]

for card in base_cards:
    card["uid"] = str(uuid.uuid4())

recipes = [
  {
    "id": "donetskyi_borscht",
    "name": "Донецький борщ",
    "ingredients": ["cabbage", "onion", "tomato_paste", "carrot", "potato", "fresh_tomato", "beet", "fish", "beef",
                    "sauerkraut"],
    "levels": {5: 4, 7: 7, 10: 9}
  },
  {
    "id": "volynskyi_borscht",
    "name": "Волинський борщ",
    "ingredients": ["cabbage", "onion", "tomato_paste", "carrot", "potato", "fresh_tomato", "beet", "prunes", "mushroom",
                    "sweet_pepper"],
    "levels": {5: 4, 7: 7, 10: 9}
  },
  {
    "id": "pisnyi_z_galushkami",
    "name": "Пісний борщ із галушками та квасом",
    "ingredients": ["cabbage", "onion", "tomato_paste", "carrot", "potato", "beet", "sweet_pepper", "celery_root",
                    "beet_kvass", "sauerkraut", "flour", "eggs"],
    "levels": {8: 3, 10: 4, 12: 6}
  },
  {
    "id": "borscht_z_baklazhanamy",
    "name": "Борщ із баклажанами",
    "ingredients": ["cabbage", "onion", "tomato_paste", "carrot", "potato", "fresh_tomato", "beet", "pork", "eggplant",
                    "beans"],
    "levels": {5: 4, 7: 6, 10: 8}
  },
  {
    "id": "poliskyi_borscht",
    "name": "Поліський борщ",
    "ingredients": ["cabbage", "onion", "carrot", "potato", "beet", "pork", "honey", "sauerkraut"],
    "levels": {4: 4, 6: 7, 8: 8}
  },
  {
    "id": "borscht_z_grushoi",
    "name": "Борщ із копченою грушею",
    "ingredients": ["cabbage", "onion", "tomato_paste", "carrot", "potato", "fresh_tomato", "beet", "sweet_pepper",
                    "pork", "smoked_pear", "celery_root"],
    "levels": {5: 4, 7: 6, 11: 8}
  },
  {
    "id": "lvivskyi_borscht",
    "name": "Львівський борщ",
    "ingredients": ["cabbage", "onion", "tomato_paste", "carrot", "potato", "fresh_tomato", "beet", "beans", "beef",
                    "mushroom"],
    "levels": {5: 4, 7: 7, 10: 9}
  },
  {
    "id": "pisnyi_z_grushoi",
    "name": "Пісний борщ із копченою грушею",
    "ingredients": ["cabbage", "onion", "tomato_paste", "carrot", "potato", "beet", "sweet_pepper",
                    "beans", "smoked_pear", "celery_root"],
    "levels": {5: 4, 7: 6, 10: 8}
  },
  {
    "id": "zhovtyi_borscht",
    "name": "Жовтий борщ",
    "ingredients": ["cabbage", "onion", "celery_root", "carrot", "potato", "fresh_tomato", "pork", "sweet_pepper",
                    "mushroom", "eggplant", "white_beet"],
    "levels": {7: 6, 9: 7, 11: 8}
  },
  {
    "id": "zakarpatskyi_borscht",
    "name": "Закарпатський борщ-бограч",
    "ingredients": ["cabbage", "onion", "tomato_paste", "carrot", "potato", "sweet_pepper", "beet", "pork",
                    "celery_root", "home_sauseges"],
    "levels": {5: 3, 7: 4, 10: 6}
  },
  {
    "id": "cherkaskyi_borscht",
    "name": "Черкаський борщ",
    "ingredients": ["cabbage", "onion", "tomato_paste", "carrot", "potato", "fresh_tomato", "beet", "fish", "flour"],
    "levels": {4: 3, 6: 4, 9: 6}
  },
  {
    "id": "odeskyi_borscht",
    "name": "Одеський борщ",
    "ingredients": ["cabbage", "onion", "carrot", "potato", "fresh_tomato", "white_beet", "fish", "sauerkraut_tomato"],
    "levels": {4: 3, 6: 5, 8: 6}
  },
  {
    "id": "borscht_z_frykadelkamy",
    "name": "Борщ із фрикадельками",
    "ingredients": ["cabbage", "onion", "carrot", "potato", "sweet_pepper", "beet", "chicken", "celery_root"],
    "levels": {4: 3, 6: 4, 8: 5}
  },
  {
    "id": "borsht_z_chornoslyvom",
    "name": "Борщ із квашеними томатами і чорносливом",
    "ingredients": ["cabbage", "onion", "tomato_paste", "carrot", "potato", "celery_root", "beet", "prunes",
                    "sauerkraut_tomato"],
    "levels": {5: 3, 7: 4, 9: 7}
  },
  {
    "id": "zelenyi_na_kuryachomu",
    "name": "Зелений борщ на курячому бульйоні",
    "ingredients": ["celery_root", "onion", "carrot", "potato", "eggs", "sorrel", "chicken"],
    "levels": {4: 3, 5: 4, 7: 7}
  },
  {
    "id": "poltavskyi_borscht",
    "name": "Полтавський борщ",
    "ingredients": ["cabbage", "onion", "sweet_pepper", "carrot", "potato", "celery_root", "beet", "pork", "eggs",
                    "flour"],
    "levels": {5: 4, 7: 6, 10: 8}
  },
  {
    "id": "frankivskyi_borscht",
    "name": "Івано-франківський борщ",
    "ingredients": ["cabbage", "onion", "tomato_paste", "carrot", "potato", "beet", "apple", "beef"],
    "levels": {4: 4, 6: 6, 8: 7}
  },
  {
    "id": "klasychnyi_zelenyi",
    "name": "Класичний зелений борщ",
    "ingredients": ["celery_root", "onion", "pork", "carrot", "potato", "sorrel", "eggs"],
    "levels": {4: 3, 5: 4, 7: 5}
  },
  {
    "id": "krymskotatarskyi_borscht",
    "name": "Кримськотатарський борщ",
    "ingredients": ["cabbage", "onion", "sweet_pepper", "carrot", "potato", "fresh_tomato", "beet", "celery_root",
                    "eggs", "lamb"],
    "levels": {5: 4, 8: 6, 10: 8}
  },
  {
    "id": "pisnyi_z_grybamy",
    "name": "Пісний борщ із грибними кльоцками",
    "ingredients": ["cabbage", "onion", "celery_root", "carrot", "potato", "eggs", "beet", "beans", "flour",
                    "mushroom"],
    "levels": {5: 4, 7: 6, 10: 8}
  },
  {
    "id": "guzulskyi_borscht",
    "name": "Гуцульський борщ",
    "ingredients": ["white_beet", "onion", "home_sauseges", "carrot", "potato", "beet_kvass", "beef"],
    "levels": {4: 3, 5: 5, 7: 6}
  },
]

skvarkas_disposable = [
    # {"id": "blackout", "type": "shkvarka", "subtype": "disposable", "name": "Блекаут", "description": "Кожен гравець може негайно викласти з руки у свій борщ 1 інгредієнт долілиць. Цей інгредієнт не можна скинути або забрати."},
    {"id": "u_komori_myshi", "type": "shkvarka", "subtype": "disposable", "name": "У коморі завелися миші", "description": "Кожен гравець скидає 2 будь-які інгредієнти з руки гравця ліворуч."},
    {"id": "garmyder_na_kuhni", "type": "shkvarka", "subtype": "disposable", "name": "Тотальний гармидер на кухні", "description": "Кожен гравець передає свою карту рецепта гравцеві ліворуч і тепер варить новий борщ. Інгредієнти, яких немає в новому рецепті, скидають."},
    {"id": "zazdrisni_susidy", "type": "shkvarka", "subtype": "disposable", "name": "Заздрісні сусіди", "description": "Гравець з найбільшою кількістю ПО скидає будь-який рідкісний інгредієнт з борщу."},
    {"id": "kuhar_rozbazikav", "type": "shkvarka", "subtype": "disposable", "name": "Балакучий кухар усе розбазікав", "description": "Усі гравці кладуть свої карти рецептів горілиць і залишають їх так до кінця партії."},
    {"id": "mityng_zahysnykiv", "type": "shkvarka", "subtype": "disposable", "name": "Мітинг захисників тварин", "description": "Кожен гравець скидає свинину або яловичину зі свого борщу."},
    {"id": "yarmarok", "type": "shkvarka", "subtype": "disposable", "name": "Ярмарок", "description": "Кожен з гравців обирає карту з руки та передає гравцю ліворуч."},
    # {"id": "zlodyi_nevdaha", "type": "shkvarka", "subtype": "disposable", "name": "Злодюжка-невдаха", "description": "Гравець з найменшою кількістю ПО може забрати у свій борщ інгредієнт з борщу іншого гравця."},
    {"id": "vtratyv_niuh", "type": "shkvarka", "subtype": "disposable", "name": "Кухар втратив нюх після ковіду", "description": "Кожен гравець скидає будь-який додатковий інгредієнт з борщу гравця праворуч."},
    {"id": "den_vrozhaiu", "type": "shkvarka", "subtype": "disposable", "name": "День збору врожаю", "description": "Кожен гравець скидає з борщу 1 інгредієнт, який зараз є на ринку."},
    {"id": "zgorila_zasmazhka", "type": "shkvarka", "subtype": "disposable", "name": "Згоріла засмажка", "description": "Всі гравці скидають цибулю та моркву зі своїх борщів."},
    {"id": "zagubyly_spysok", "type": "shkvarka", "subtype": "disposable", "name": "Загубили список покупок", "description": "Кожен гравець скидає з борщу 1 інгредієнт, якого зараз немає на ринку."},
    {"id": "rozsypaly_specii", "type": "shkvarka", "subtype": "disposable", "name": "Розсипали спеції", "description": "Кожен гравець скидає інгредієнт з борщу гравця ліворуч (той може захиститися сметаною)."},
    {"id": "postachalnyk_pereplutav", "type": "shkvarka", "subtype": "disposable", "name": "Постачальник усе переплутав", "description": "Починаючи з активного гравця, кожен по черзі скидає всі карти з руки та бере 5 нових з колоди."},

]
skvarkas_permanent = [
    {"id": "defolt_crisa", "type": "shkvarka", "subtype": "permanent", "name": "Дефолт, криза, інфляція", "description": "Відтепер під час обміну на ринку треба платити на 1 більше."},
    {"id": "sanepidemstancia", "type": "shkvarka", "subtype": "permanent", "name": "Санепідемстанція закрила ринок", "description": "Активний гравець скидає з ринку 2 будь-які інгредієнти. Відтепер ринок має на 2 інгредієнти менше."},
    {"id": "kayenskyi_perec", "type": "shkvarka", "subtype": "permanent", "name": "Закупили каєнський перець", "description": "Відтепер ефект перцю вогник - забрати / скинути 2 інгредієнти замість 1."},
    {"id": "porvalas_torbynka", "type": "shkvarka", "subtype": "permanent", "name": "Порвалася торбинка", "description": "Відтепер кожен гравець може мати на руці не більше ніж 4 карти. Гравці повинні негайно скинути зайві карти на свій вибір."},
    {"id": "peresolyly", "type": "shkvarka", "subtype": "permanent", "name": "Пересолили", "description": "Відтепер не можна додавати в борщ нові додаткові інгредієнти (уже додані інгредієнти залишаються)."},
    {"id": "molochka_skysla", "type": "shkvarka", "subtype": "permanent", "name": "Молочка скисла", "description": "Відтепер для захисту від будь-якого перцю треба грати 2 сметани."},
]