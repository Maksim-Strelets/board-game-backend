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
    *[{"id": "beaf", "type": "rare", "name": "Яловичина", "cost": 3, "points": 2} for _ in range(4)],
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
    *[{"id": "salt", "type": "extra", "name": "Сіль", "cost": 1, "points": 2} for _ in range(3)],
    *[{"id": "garlic", "type": "extra", "name": "Часник", "cost": 5, "points": 4} for _ in range(2)],
    *[{"id": "vinnik_lard", "type": "extra", "name": "Вінницьке сало", "cost": 6, "points": 0, "effect_description": ""} for _ in range(2)],  # TODO: desc
    *[{"id": "rye_bread", "type": "extra", "name": "Житній хлібчик", "cost": 6, "points": 5} for _ in range(2)],
    *[{"id": "bay_leaf", "type": "extra", "name": "Лавровий лист", "cost": 4, "points": 3} for _ in range(2)],
    *[{"id": "vitamin_bunch", "type": "extra", "name": "Вітамінний пучок", "cost": 2, "points": 2} for _ in range(2)],

    # special
    *[{"id": "chili_pepper", "type": "special", "name": "Перець вогник", "cost": 4, "effect": "steal_or_discard", "effect_description": "Перемістіть у свій борщ або скиньте будь-який інгредієнт з борщу іншого гравця."} for _ in range(6)],
    *[{"id": "black_pepper", "type": "special", "name": "Чорний перець", "cost": 3, "effect": "discard_or_take", "effect_description": "Скиньте 1 інгредієнт з борщу кожного суперника АБО заеріть по 1 випадковій карті з руки кожного суперника."} for _ in range(4)],
    *[{"id": "sour_cream", "type": "special", "name": "Сметана", "cost": 4, "effect": "defense", "effect_description": "Скиньте, щоб захиститись від ефектів карт «Чорний перець» або «Перець вогник»."} for _ in range(4)],
    *[{"id": "ginger", "type": "special", "name": "Імбир", "cost": 3, "effect": "take_market", "effect_description": "Візьміть на руку 2 будь-які інгредієнти з ринку і поповніть ринок."} for _ in range(3)],
    *[{"id": "cinnamon", "type": "special", "name": "Кориця", "cost": 5, "effect": "take_discard", "effect_description": "Перегляньте скид і візьміть на руку 1 карту інгредієнта."} for _ in range(3)],
    *[{"id": "olive_oil", "type": "special", "name": "Оливкова олія", "cost": 3, "effect": "look_top_5", "effect_description": "Перегляньте 5 верхніх карт у колоді інгредієнтів. Візьміть на руку 2 карти, інші 3 поверніть у колоду."} for _ in range(300)],
    *[{"id": "paprika", "type": "special", "name": "Паприка", "cost": 4, "effect": "refresh_market", "effect_description": "Оновіть ринок. Після цього можете виконати обмін."} for _ in range(3)],
]

for card in base_cards:
    card["uid"] = str(uuid.uuid4())

recipes = [
  {
    "id": "donetskyi_borscht",
    "name": "Донецький борщ",
    "ingredients": ["cabbage", "onion", "tomato_paste", "carrot", "potato", "fresh_tomato", "beet", "fish", "beaf",
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
                    "beens"],
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
    "ingredients": ["cabbage", "onion", "tomato_paste", "carrot", "potato", "fresh_tomato", "beet", "beens", "beaf",
                    "mushroom"],
    "levels": {5: 4, 7: 7, 10: 9}
  },
  {
    "id": "pisnyi_z_grushoi",
    "name": "Пісний борщ із копченою грушею",
    "ingredients": ["cabbage", "onion", "tomato_paste", "carrot", "potato", "beet", "sweet_pepper",
                    "beens", "smoked_pear", "celery_root"],
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
    "ingredients": ["cabbage", "onion", "tomato_paste", "carrot", "potato", "beet", "apple", "beaf"],
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
    "ingredients": ["cabbage", "onion", "celery_root", "carrot", "potato", "eggs", "beet", "beens", "flour",
                    "mushroom"],
    "levels": {5: 4, 7: 6, 10: 8}
  },
  {
    "id": "guzulskyi_borscht",
    "name": "Гуцульський борщ",
    "ingredients": ["white_beet", "onion", "home_sauseges", "carrot", "potato", "beet_kvass", "beaf"],
    "levels": {4: 3, 5: 5, 7: 6}
  },
]

skvarkas_disposable = []
skvarkas_permanent = []