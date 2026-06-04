"""Terraria (Calamity) boss progression loadout data and source metadata."""

import re
from typing import Optional

BOSS_DISPLAY_NAMES = {
    "desert_scourge": "Desert Scourge",
    "crabulon": "Crabulon",
    "hive_mind": "Hive Mind",
    "perforators": "The Perforators",
    "slime_god": "The Slime God",
    "wall_of_flesh": "Wall of Flesh",
    "cryogen": "Cryogen",
    "plantera": "Plantera",
    "moon_lord": "Moon Lord",
}


BOSS_ALIASES = {
    "desert scourge": "desert_scourge",
    "desertscourge": "desert_scourge",
    "사막스컬지": "desert_scourge",
    "사막 스컬지": "desert_scourge",
    "crabulon": "crabulon",
    "크라불론": "crabulon",
    "hive mind": "hive_mind",
    "hivemind": "hive_mind",
    "하이브마인드": "hive_mind",
    "하이브 마인드": "hive_mind",
    "perforators": "perforators",
    "the perforators": "perforators",
    "퍼포레이터": "perforators",
    "퍼포레이터즈": "perforators",
    "slime god": "slime_god",
    "the slime god": "slime_god",
    "슬라임갓": "slime_god",
    "슬라임 갓": "slime_god",
    "wall of flesh": "wall_of_flesh",
    "wof": "wall_of_flesh",
    "월오플": "wall_of_flesh",
    "육괴": "wall_of_flesh",
    "wallofflesh": "wall_of_flesh",
    "cryogen": "cryogen",
    "크라이오젠": "cryogen",
    "plantera": "plantera",
    "플랜테라": "plantera",
    "moon lord": "moon_lord",
    "moonlord": "moon_lord",
    "문로드": "moon_lord",
    "문 로드": "moon_lord",
}


CLASS_DISPLAY_NAMES = {
    "melee": "워리어",
    "ranged": "레인저",
    "mage": "소서러",
    "summoner": "서머너",
    "rogue": "로그",
}


CLASS_ALIASES = {
    "근접": "melee",
    "전사": "melee",
    "워리어": "melee",
    "warrior": "melee",
    "melee": "melee",
    "원거리": "ranged",
    "레인저": "ranged",
    "헌터": "ranged",
    "ranger": "ranged",
    "ranged": "ranged",
    "마법": "mage",
    "메이지": "mage",
    "소서러": "mage",
    "위저드": "mage",
    "mage": "mage",
    "sorcerer": "mage",
    "wizard": "mage",
    "소환": "summoner",
    "서머너": "summoner",
    "summoner": "summoner",
    "도적": "rogue",
    "로그": "rogue",
    "rogue": "rogue",
}

MATERIAL_ALIASES = {
    "에어라이트": "aerialite_bar",
    "에어라이트바": "aerialite_bar",
    "aerialite": "aerialite_bar",
    "aerialite bar": "aerialite_bar",
    "크라이오닉오어": "cryonic_ore",
    "크라이오닉 ore": "cryonic_ore",
    "cryonic ore": "cryonic_ore",
    "율리블룸오어": "uelibloom_ore",
    "uelibloom ore": "uelibloom_ore",
    "스코리아오어": "scoria_ore",
    "scoria ore": "scoria_ore",
    "아스트랄오어": "astral_ore",
    "astral ore": "astral_ore",
    "엑소디움클러스터": "exodium_cluster",
    "exodium cluster": "exodium_cluster",
    "루미나이트바": "luminite_bar",
    "luminite bar": "luminite_bar",
    "코스밀라이트바": "cosmilite_bar",
    "cosmilite bar": "cosmilite_bar",
    "아우리크오어": "auric_ore",
    "auric ore": "auric_ore",
    "아우리크바": "auric_bar",
    "auric bar": "auric_bar",
    "쉐도우스펙바": "shadowspec_bar",
    "shadowspec bar": "shadowspec_bar",
    "블러드스톤": "bloodstone",
    "bloodstone": "bloodstone",
    "디바인지오드": "divine_geode",
    "divine geode": "divine_geode",
    "리퍼투스": "reaper_tooth",
    "reaper tooth": "reaper_tooth",
}

MATERIAL_GUIDES = {
    "aerialite_bar": {
        "name": "Aerialite Bar",
        "recipe": "Aerialite Ore 제련 (Furnace 계열).",
        "how_to_get": "Hive Mind 또는 Perforators 처치 후 에어라이트 광맥 채굴 가능.",
        "tips": "Pre-Skeletron 구간 핵심 재료. 이동/회피 보조 장비 라인으로 자주 연결됨.",
    },
    "cryonic_ore": {
        "name": "Cryonic Ore",
        "recipe": "조합 재료로 사용 (직접 제련보다 제작 트리에서 소모).",
        "how_to_get": "Cryogen 처치 후 얼음 지형에서 채굴 가능.",
        "tips": "하드모드 중반 무기/장비 업그레이드 분기점 재료.",
    },
    "uelibloom_ore": {
        "name": "Uelibloom Ore",
        "recipe": "Uelibloom Bar 제작 재료.",
        "how_to_get": "Providence 처치 후 정글 지하에서 채굴 가능.",
        "tips": "Post-Moon Lord 초중반 장비(특히 Tarragon 라인) 핵심 재료.",
    },
    "scoria_ore": {
        "name": "Scoria Ore",
        "recipe": "Scoria Bar 제작 재료.",
        "how_to_get": "Golem 처치 후 Abyss 심층부(3층)에서 채굴 가능.",
        "tips": "Post-Golem 단계 각 직업 무기 교체 타이밍에 많이 사용.",
    },
    "astral_ore": {
        "name": "Astral Ore",
        "recipe": "Astral Bar 제작 재료.",
        "how_to_get": "Astrum Deus 처치 후 Astral Infection 지역에서 채굴 가능.",
        "tips": "Pre-Moon Lord 후반~Post-Moon Lord 초반 연결 재료.",
    },
    "exodium_cluster": {
        "name": "Exodium Cluster",
        "recipe": "Exo 계열 제작 재료로 직접 소모됨.",
        "how_to_get": "Moon Lord 이후 하늘섬/우주 구간에서 Exodium 클러스터 채굴.",
        "tips": "Post-Moon Lord 진입 직후 이동/보조 장비 제작에 자주 사용.",
    },
    "luminite_bar": {
        "name": "Luminite Bar",
        "recipe": "Luminite 4개 + Ancient Manipulator.",
        "how_to_get": "Moon Lord 처치 보상 Luminite를 제련.",
        "tips": "Post-Moon Lord 시작 장비 트리의 베이스 재료.",
    },
    "cosmilite_bar": {
        "name": "Cosmilite Bar",
        "recipe": "Cosmilite Slag 제련/제작 라인.",
        "how_to_get": "Devourer of Gods 처치 이후 관련 재료 해금.",
        "tips": "Pre-Yharon 구간 상위 무기/방어구 제작 핵심.",
    },
    "auric_ore": {
        "name": "Auric Ore",
        "recipe": "Auric Bar 제작 재료.",
        "how_to_get": "Yharon 처치 후 지하에서 생성/채굴 가능.",
        "tips": "최종급 장비 직전 관문 재료.",
    },
    "auric_bar": {
        "name": "Auric Bar",
        "recipe": "Auric Ore + Yharon Soul Fragment 계열 재료 조합.",
        "how_to_get": "Yharon 이후 제작 가능.",
        "tips": "Auric Tesla 계열 장비 및 최종 무기군 핵심 재료.",
    },
    "shadowspec_bar": {
        "name": "Shadowspec Bar",
        "recipe": "Exo Prisms + Ashes of Annihilation + Auric Bar 조합.",
        "how_to_get": "Exo Mechs / Supreme Witch, Calamitas 처치 이후 최종 제작 해금.",
        "tips": "엔드게임/개발자급 아이템 및 Boss Rush 준비 단계 핵심.",
    },
    "bloodstone": {
        "name": "Bloodstone",
        "recipe": "다수 Post-Providence 장비 제작 재료.",
        "how_to_get": "Providence 이후 Brimstone Crag 적 및 Ravager 관련 루트에서 획득.",
        "tips": "Polterghast 전 구간 장비 갱신에 중요.",
    },
    "divine_geode": {
        "name": "Divine Geode",
        "recipe": "Tarragon 및 Post-Providence 제작 재료.",
        "how_to_get": "Providence 처치 이후 드롭/채집 루트 해금.",
        "tips": "Uelibloom과 함께 Post-Moon Lord 초반 핵심 재료.",
    },
    "reaper_tooth": {
        "name": "Reaper Tooth",
        "recipe": "상위 관통/방어 관통 계열 장비 제작 재료.",
        "how_to_get": "Abyss 심층 미니보스/적 루트에서 획득 (Polterghast 이후 단계 추천).",
        "tips": "고난도 보스에서 방어 관통 세팅을 맞출 때 효율이 큼.",
    },
}


POST_BOSS_LOADOUTS = {
    "desert_scourge": {
        "melee": {
            "weapons": ["Bladecrest Oathsword", "Sea Sword"],
            "armor": ["Victide Armor"],
            "accessories": ["Fungal Clump", "Counter Scarf", "Cloud in a Bottle"],
            "next_goal": "Crabulon 또는 Hive Mind/Perforators 준비",
        },
        "ranged": {
            "weapons": ["Aquashard Shotgun", "Storm Surge"],
            "armor": ["Victide Armor"],
            "accessories": ["Shark Tooth Necklace", "Frostspark Boots", "Rusty Medallion"],
            "next_goal": "Crabulon 처치 후 Fungicide 파밍",
        },
        "mage": {
            "weapons": ["Turbulance", "Water Bolt"],
            "armor": ["Victide Armor"],
            "accessories": ["Mana Flower", "Fungal Clump", "Cloud in a Bottle"],
            "next_goal": "Evil 보스 처치 후 마나 계열 업그레이드",
        },
        "summoner": {
            "weapons": ["Sun Spirit Staff", "Belladonna Spirit Staff"],
            "armor": ["Wulfrum Armor"],
            "accessories": ["Feral Claws", "Spirit Glyph", "Frostspark Boots"],
            "next_goal": "Hive Mind/Perforators 후 Hive Pod 계열 확보",
        },
        "rogue": {
            "weapons": ["Crystalline", "Scourge of the Desert"],
            "armor": ["Victide Armor"],
            "accessories": ["Gleaming Dagger", "Counter Scarf", "Frostspark Boots"],
            "next_goal": "Slime God 전까지 stealth 보조 악세 강화",
        },
    },
    "slime_god": {
        "melee": {
            "weapons": ["Carnage", "The Gods Gambit"],
            "armor": ["Aerospec Armor"],
            "accessories": ["Bloody Worm Scarf", "Counter Scarf", "Frog Leg"],
            "next_goal": "Wall of Flesh 진입 전 Hellstone/Underworld 파밍",
        },
        "ranged": {
            "weapons": ["Goobow", "Aerialite Bow"],
            "armor": ["Aerospec Armor"],
            "accessories": ["Luxor's Gift", "Shield of Cthulhu", "Frostspark Boots"],
            "next_goal": "Wall of Flesh 처치 후 Daedalus 계열 교체",
        },
        "mage": {
            "weapons": ["Fractal Cane", "Black Anurian"],
            "armor": ["Aerospec Armor"],
            "accessories": ["Mana Flower", "Luxor's Gift", "Counter Scarf"],
            "next_goal": "Hardmode 진입 후 Crystal Serpent 계열 확보",
        },
        "summoner": {
            "weapons": ["Caustic Staff", "Imp Staff"],
            "armor": ["Statigel Armor"],
            "accessories": ["Spirit Glyph", "Stinger Necklace", "Frostspark Boots"],
            "next_goal": "Wall of Flesh 이후 Spider 세트 준비",
        },
        "rogue": {
            "weapons": ["Tracking Disk", "Meteor Fist"],
            "armor": ["Statigel Armor"],
            "accessories": ["Gleaming Dagger", "Counter Scarf", "Frog Leg"],
            "next_goal": "Hardmode 광석 루트로 stealth 딜 세팅 전환",
        },
    },
    "wall_of_flesh": {
        "melee": {
            "weapons": ["Palladium Pike", "Ice Sickle"],
            "armor": ["Daedalus Armor"],
            "accessories": ["Warrior Emblem", "Frostspark Boots", "Counter Scarf"],
            "next_goal": "Cryogen 처치 전 기계 보스 대비",
        },
        "ranged": {
            "weapons": ["Clockwork Assault Rifle", "Daedalus Stormbow"],
            "armor": ["Daedalus Armor"],
            "accessories": ["Ranger Emblem", "Magic Quiver", "Frostspark Boots"],
            "next_goal": "Cryogen 후 Hallowed 업그레이드 준비",
        },
        "mage": {
            "weapons": ["Crystal Serpent", "Sky Fracture"],
            "armor": ["Daedalus Armor"],
            "accessories": ["Sorcerer Emblem", "Mana Flower", "Celestial Cuffs"],
            "next_goal": "Cryogen 보상으로 마법 무기 단계 업그레이드",
        },
        "summoner": {
            "weapons": ["Spider Staff", "Sanguine Staff"],
            "armor": ["Spider Armor"],
            "accessories": ["Summoner Emblem", "Pygmy Necklace", "Frostspark Boots"],
            "next_goal": "Cryogen 이후 Summoner Hardmode 세트 진입",
        },
        "rogue": {
            "weapons": ["Titan Heart", "Blast Barrel"],
            "armor": ["Titan Heart Armor"],
            "accessories": ["Rogue Emblem", "Evasion Scarf", "Frostspark Boots"],
            "next_goal": "Cryogen 이후 Kelvin Catalyst 계열 파밍",
        },
    },
    "cryogen": {
        "melee": {
            "weapons": ["Kelvin Catalyst", "True Caustic Edge"],
            "armor": ["Orichalcum Armor"],
            "accessories": ["Warrior Emblem", "Bloody Worm Scarf", "Charm of Myths"],
            "next_goal": "Plantera 전 Calamitas Clone/Brimstone 루트 파밍",
        },
        "ranged": {
            "weapons": ["Pearl God", "Flak Toxicannon"],
            "armor": ["Orichalcum Armor"],
            "accessories": ["Ranger Emblem", "Magic Quiver", "Frostspark Boots"],
            "next_goal": "Plantera 진입 전 탄약/버프 최적화",
        },
        "mage": {
            "weapons": ["Frigidflash Bolt", "Crystal Storm"],
            "armor": ["Forbidden Armor"],
            "accessories": ["Sorcerer Emblem", "Mana Flower", "Celestial Cuffs"],
            "next_goal": "Plantera 직전 광역기/단일딜 무기 2셋 준비",
        },
        "summoner": {
            "weapons": ["Cold Divinity", "Ancient Ice Chunk"],
            "armor": ["Spider Armor"],
            "accessories": ["Summoner Emblem", "Pygmy Necklace", "Spirit Glyph"],
            "next_goal": "Plantera 전 Blade Staff 또는 대체 미니언 확보",
        },
        "rogue": {
            "weapons": ["Prismalline", "Equanimity"],
            "armor": ["Titan Heart Armor"],
            "accessories": ["Rogue Emblem", "Gleaming Dagger", "Counter Scarf"],
            "next_goal": "Plantera 이후 Celestial Reaper 루트 준비",
        },
    },
    "plantera": {
        "melee": {
            "weapons": ["True Ark of the Ancients", "Terra Blade"],
            "armor": ["Hydrothermic Armor"],
            "accessories": ["Fire Gauntlet", "Asgard's Valor", "Angel Treads"],
            "next_goal": "Lunar 이벤트 및 Moon Lord 준비",
        },
        "ranged": {
            "weapons": ["P90", "Megashark (Chlorophyte Bullets)"],
            "armor": ["Hydrothermic Armor"],
            "accessories": ["Sniper Scope", "Asgard's Valor", "Angel Treads"],
            "next_goal": "Moon Lord 대비 단일딜 무기 업그레이드",
        },
        "mage": {
            "weapons": ["Magnet Sphere", "Venusian Trident"],
            "armor": ["Hydrothermic Armor"],
            "accessories": ["Celestial Emblem", "Asgard's Valor", "Mana Flower"],
            "next_goal": "Lunar Pillar 단계별 속성 무기 준비",
        },
        "summoner": {
            "weapons": ["Xeno Staff", "Terraprisma (가능 시)"],
            "armor": ["Spooky Armor"],
            "accessories": ["Papyrus Scarab", "Asgard's Valor", "Necromantic Scroll"],
            "next_goal": "Moon Lord 전 버프/소환 수 상한 최적화",
        },
        "rogue": {
            "weapons": ["Malachite", "Fantasy Talisman"],
            "armor": ["Hydrothermic Armor"],
            "accessories": ["Rogue Emblem", "Asgard's Valor", "Angel Treads"],
            "next_goal": "Moon Lord 단계 stealth burst 세팅 완성",
        },
    },
    "moon_lord": {
        "melee": {
            "weapons": ["Ark of the Cosmos", "Galaxia"],
            "armor": ["Bloodflare Armor"],
            "accessories": ["The Community", "Asgardian Aegis", "Elysian Wings"],
            "next_goal": "Providence 진입 전 엔드게임 버프 파밍",
        },
        "ranged": {
            "weapons": ["Vortexpopper", "Monsoon"],
            "armor": ["Bloodflare Armor"],
            "accessories": ["The Community", "Elemental Quiver", "Elysian Wings"],
            "next_goal": "Providence 대비 관통/단일딜 세트 분리",
        },
        "mage": {
            "weapons": ["Effervescence", "Ultra Liquidator"],
            "armor": ["Bloodflare Armor"],
            "accessories": ["The Community", "Sigil of Calamitas", "Mana Flower"],
            "next_goal": "Providence 진입 전 생존 악세 우선 보강",
        },
        "summoner": {
            "weapons": ["Stardust Dragon Staff", "Resurrection Butterfly"],
            "armor": ["Bloodflare Armor"],
            "accessories": ["The Community", "Nucleogenesis", "Elysian Wings"],
            "next_goal": "Post-Moon Lord 미니언/센트리 병행 세팅",
        },
        "rogue": {
            "weapons": ["Executioner's Blade", "Valediction"],
            "armor": ["Bloodflare Armor"],
            "accessories": ["The Community", "Dark God's Sheath", "Elysian Wings"],
            "next_goal": "Providence 기준 stealth burst + 유지딜 이원화",
        },
    },
}

# Source-validated baseline rebuilt from official wiki guides.
# Primary references:
# - Guide:Class_setups/Pre-Hardmode (oldid=291534)
# - Guide:Class_setups/Hardmode (oldid=290411)
# - Guide:Class_setups/Post-Moon_Lord (oldid=290342)
# - Armor progression pages for each phase
SOURCE_VALIDATED_POST_BOSS_LOADOUTS = {
    "desert_scourge": {
        "__meta__": {
            "stage": "Post-Eye of Cthulhu and Desert Scourge",
            "source_note": "Calamity Guide:Armor progression/Pre-Hardmode 구간",
        },
        "melee": {
            "weapons": ["Perfect Dark (퍼펙트 다크)", "Vein Burster (베인 버스터)"],
            "armor": ["Victide Shellmet + Victide Breastplate + Victide Greaves"],
            "accessories": ["Bundle of Horseshoe Balloons", "Unholy Tonic / Vicious Tonic", "Healing Potions / Strange Brew"],
            "next_goal": "Eater of Worlds / Brain of Cthulhu 이후 Hive Mind 또는 Perforators 준비",
        },
        "ranged": {
            "weapons": ["Demon Bow / Tendon Bow (데몬 보우 / 텐던 보우)"],
            "armor": ["Victide Coral Turban + Victide Breastplate + Victide Greaves"],
            "accessories": ["Bundle of Horseshoe Balloons", "Unholy Tonic / Vicious Tonic", "Musket Ball / Tungsten Bullet"],
            "next_goal": "Pre-The Hive Mind/The Perforators 단계 장비로 전환",
        },
        "mage": {
            "weapons": ["Magna Cannon (마그나 캐논)", "Opal Striker (오팔 스트라이커)"],
            "armor": ["Victide Hermit Helmet + Victide Breastplate + Victide Greaves", "Wizard Hat + Mystic Robe + Meteor Leggings"],
            "accessories": ["Mana Flower / Magic Cuffs", "Bundle of Horseshoe Balloons", "Unholy Tonic / Vicious Tonic"],
            "next_goal": "Hive Mind/Perforators 전 Meteor 계열 + 마나 악세 보강",
        },
        "summoner": {
            "weapons": ["Brittle Star Staff / Wulfrum Controller (브리틀 스타 스태프 / 울프럼 컨트롤러)"],
            "armor": ["Wulfrum Hat & Goggles + Wulfrum Jacket + Wulfrum Overalls", "Victide Mask + Victide Breastplate + Victide Greaves"],
            "accessories": ["Bundle of Horseshoe Balloons", "Unholy Tonic / Vicious Tonic", "Healing Potions / Strange Brew"],
            "next_goal": "Post-Evil Boss 2 구간에서 Aerospec/Bee 계열로 교체",
        },
        "rogue": {
            "weapons": ["Scourge of the Desert (스컬지 오브 더 데저트)", "Gilded / Gleaming Dagger (길디드 / 글리밍 대거)"],
            "armor": ["Victide Headcrab + Victide Breastplate + Victide Greaves"],
            "accessories": ["Bundle of Horseshoe Balloons", "Unholy Tonic / Vicious Tonic", "Healing Potions / Strange Brew"],
            "next_goal": "Slime God 이전까지 stealth 중심 세팅 유지",
        },
    },
    "slime_god": {
        "__meta__": {
            "stage": "Post-Slime God",
            "source_note": "Calamity Guide:Armor progression/Pre-Hardmode 구간",
        },
        "melee": {
            "weapons": ["Perfect Dark / Vein Burster (퍼펙트 다크 / 베인 버스터)"],
            "armor": ["Statigel Helm + Statigel Armor + Statigel Greaves", "Molten Helmet + Molten Breastplate + Molten Greaves"],
            "accessories": ["Bundle of Horseshoe Balloons", "Crown Jewel / Honey Dew", "Honeyfins / Restoration Potions"],
            "next_goal": "Wall of Flesh 진입 전 던전/심연/브림스톤 크래그 파밍",
        },
        "ranged": {
            "weapons": ["Demon Bow (데몬 보우)", "Tendon Bow (텐던 보우)", "Musket Balls / Tungsten Bullets (머스킷 탄환 / 텅스텐 탄환)"],
            "armor": ["Statigel Headgear + Statigel Armor + Statigel Greaves"],
            "accessories": ["Bundle of Horseshoe Balloons", "Crown Jewel / Honey Dew", "Musket Balls / Tungsten Bullets"],
            "next_goal": "Wall of Flesh 후 Hardmode 탄약/악세 전환",
        },
        "mage": {
            "weapons": ["Magna Cannon / Opal Striker (마그나 캐논 / 오팔 스트라이커)"],
            "armor": ["Statigel Cap + Statigel Armor + Statigel Greaves", "Wizard Hat + Mystic Robe + Meteor Leggings"],
            "accessories": ["Mana Flower / Magic Cuffs", "Bundle of Horseshoe Balloons", "Crown Jewel / Honey Dew"],
            "next_goal": "Hardmode 진입 직후 생존 악세 + 마나 회복 수단 보강",
        },
        "summoner": {
            "weapons": ["P-PMA: Aqueous Hunter Drone (수중 헌터 드론)"],
            "armor": ["Statigel Hood + Statigel Armor + Statigel Greaves"],
            "accessories": ["Bundle of Horseshoe Balloons", "Crown Jewel / Honey Dew", "Honeyfins / Restoration Potions"],
            "next_goal": "Wall of Flesh 이후 Spider 계열 및 Daedalus 계열 검토",
        },
        "rogue": {
            "weapons": ["Rot Ball / Tooth Ball (롯 볼 / 투스 볼)"],
            "armor": ["Statigel Mask + Statigel Armor + Statigel Greaves"],
            "accessories": ["Bundle of Horseshoe Balloons", "Crown Jewel / Honey Dew", "Honeyfins / Restoration Potions"],
            "next_goal": "Hardmode에서는 Titan Heart 중심 stealth 세팅 전환",
        },
    },
    "wall_of_flesh": {
        "__meta__": {
            "stage": "Hardmode / Pre-Mechanical Bosses",
            "source_note": "Calamity Guide:Class setups/Hardmode + Armor progression/Hardmode",
        },
        "melee": {
            "weapons": ["Flask of Cursed Flames / Flask of Ichor (저주불꽃 플라스크 / 아이코르 플라스크)", "Dart Pistol / Dart Rifle (다트 피스톨 / 다트 라이플)"],
            "armor": ["Statigel Helm + Mollusk Shellplate + Mollusk Shelleggings"],
            "accessories": ["Counter Scarf / Deep Diver", "Fairy Boots / Terraspark Boots", "Honey Dew / Radiant Ooze"],
            "next_goal": "Cryogen 또는 Queen Slime 처치 후 1기계보스 진행",
        },
        "ranged": {
            "weapons": ["Dart Pistol / Dart Rifle (다트 피스톨 / 다트 라이플)"],
            "armor": ["Statigel Headgear + Mollusk Shellplate + Mollusk Shelleggings"],
            "accessories": ["Counter Scarf / Deep Diver", "Fairy Boots / Terraspark Boots", "Cursed / Ichor 계열 탄약"],
            "next_goal": "기계보스 1킬 후 2티어 하드모드 광물 장비로 교체",
        },
        "mage": {
            "weapons": ["Cool Whip (쿨 휩)", "Firecracker (파이어크래커)"],
            "armor": ["Statigel Cap + Mollusk Shellplate + Mollusk Shelleggings"],
            "accessories": ["Counter Scarf / Deep Diver", "Fairy Boots / Terraspark Boots", "Honey Dew / Radiant Ooze"],
            "next_goal": "기계보스 진행 후 Forbidden/Daedalus/Chlorophyte 계열 검토",
        },
        "summoner": {
            "weapons": ["Cool Whip / Firecracker (쿨 휩 / 파이어크래커)"],
            "armor": ["Spider Mask + Spider Breastplate + Spider Greaves"],
            "accessories": ["Counter Scarf / Deep Diver", "Fairy Boots / Terraspark Boots", "Honey Dew / Radiant Ooze"],
            "next_goal": "Post-Mechs and Cryogen 단계에서 Daedalus/Forbidden 선택",
        },
        "rogue": {
            "weapons": ["Scourge of the Seas (스컬지 오브 더 시즈)"],
            "armor": ["Titan Heart Mask + Titan Heart Mantle + Titan Heart Boots"],
            "accessories": ["Counter Scarf / Deep Diver", "Fairy Boots / Terraspark Boots", "Honey Dew / Radiant Ooze"],
            "next_goal": "기계보스 진행 후 Daedalus Facemask 또는 Umbraphile 루트 준비",
        },
    },
    "cryogen": {
        "__meta__": {
            "stage": "Post-Mechs and Cryogen",
            "source_note": "Calamity Guide:Armor progression/Hardmode 구간",
        },
        "melee": {
            "weapons": ["Flask of Cursed Flames / Flask of Ichor (저주불꽃 플라스크 / 아이코르 플라스크)", "Ark of the Ancients (고대의 방주)"],
            "armor": ["Chlorophyte armor", "Reaver Helm + Reaver Scale Mail + Reaver Cuisses"],
            "accessories": ["Evasion Scarf / Ornate Shield", "Fairy Boots / Terraspark Boots", "Honey Dew / Radiant Ooze"],
            "next_goal": "Plantera 및 Calamitas Clone 전후 Reaver 중심으로 전환",
        },
        "ranged": {
            "weapons": ["Dart Pistol / Dart Rifle (다트 피스톨 / 다트 라이플)", "Ichor Bullets / Cursed Bullets (아이코르 탄환 / 저주 탄환)"],
            "armor": ["Chlorophyte armor", "Reaver Helm + Reaver Scale Mail + Reaver Cuisses"],
            "accessories": ["Evasion Scarf / Ornate Shield", "Fairy Boots / Terraspark Boots", "Ichor / Cursed Bullets"],
            "next_goal": "Post-Plantera에서 고화력 원거리 세트로 교체",
        },
        "mage": {
            "weapons": ["Staff of the Frost Hydra (서리 히드라 지팡이)", "Dark Harvest / Kaleidoscope (다크 하베스트 / 칼레이도스코프)"],
            "armor": ["Brimflame armor", "Spectre armor"],
            "accessories": ["Evasion Scarf / Ornate Shield", "Fairy Boots / Terraspark Boots", "Honey Dew / Radiant Ooze"],
            "next_goal": "Plantera 이후 Spectre/Brimflame 세팅 안정화",
        },
        "summoner": {
            "weapons": ["Cool Whip / Firecracker"],
            "armor": ["Daedalus Mask + Daedalus Breastplate + Daedalus Leggings", "Spider Mask + Spider Breastplate + Spider Greaves"],
            "accessories": ["Evasion Scarf / Ornate Shield", "Fairy Boots / Terraspark Boots", "Honey Dew / Radiant Ooze"],
            "next_goal": "Post-Plantera에서 Spooky 또는 Tiki로 전환",
        },
        "rogue": {
            "weapons": ["Scourge of the Seas (스컬지 오브 더 시즈)", "Flask of Cursed Flames / Flask of Ichor (저주불꽃 플라스크 / 아이코르 플라스크)"],
            "armor": ["Daedalus Facemask + Daedalus Breastplate + Daedalus Leggings", "Titan Heart Mask + Titan Heart Mantle + Titan Heart Boots"],
            "accessories": ["Evasion Scarf / Ornate Shield", "Fairy Boots / Terraspark Boots", "Honey Dew / Radiant Ooze"],
            "next_goal": "Plantera 이후 Umbraphile 세트 확보",
        },
    },
    "plantera": {
        "__meta__": {
            "stage": "Post-Plantera and Calamitas Clone / Post-Golem",
            "source_note": "Calamity Guide:Armor progression/Hardmode 구간",
        },
        "melee": {
            "weapons": ["Ark of the Ancients (고대의 방주)"],
            "armor": ["Reaver Helm + Reaver Scale Mail + Reaver Cuisses", "Hydrothermic armor"],
            "accessories": ["Asgard's Valor / Master Ninja Gear", "Angel Treads / Fairy Boots", "Sand Shark Tooth Necklace"],
            "next_goal": "Lunar Events 전 Plaguebringer Goliath, Duke Fishron, Ravager 준비",
        },
        "ranged": {
            "weapons": ["Dart Pistol / Dart Rifle (다트 피스톨 / 다트 라이플)", "Ichor Bullets / Cursed Bullets (아이코르 탄환 / 저주 탄환)"],
            "armor": ["Reaver Helm + Reaver Scale Mail + Reaver Cuisses", "Hydrothermic armor"],
            "accessories": ["Asgard's Valor / Master Ninja Gear", "Angel Treads / Fairy Boots", "Sand Shark Tooth Necklace"],
            "next_goal": "Pre-Moon Lord 단계에서 Astral/Vortex 계열 교체",
        },
        "mage": {
            "weapons": ["Staff of the Frost Hydra (서리 히드라 지팡이)", "Dark Harvest / Morning Star (다크 하베스트 / 모닝 스타)"],
            "armor": ["Brimflame armor", "Spectre armor", "Hydrothermic armor"],
            "accessories": ["Asgard's Valor / Master Ninja Gear", "Angel Treads / Fairy Boots", "Eye of the Golem"],
            "next_goal": "Lunar 이벤트 단계에서 Nebula 중심 세팅 준비",
        },
        "summoner": {
            "weapons": ["Staff of the Frost Hydra (서리 히드라 지팡이)", "Dark Harvest / Kaleidoscope (다크 하베스트 / 칼레이도스코프)"],
            "armor": ["Spooky Helmet + Spooky Breastplate + Spooky Leggings", "Plaguebringer Visor + Plaguebringer Carapace + Plaguebringer Pistons"],
            "accessories": ["Asgard's Valor / Master Ninja Gear", "Angel Treads / Fairy Boots", "Sand Shark Tooth Necklace"],
            "next_goal": "Moon Lord 전 Stardust/강화 소환 세팅으로 전환",
        },
        "rogue": {
            "weapons": ["Scourge of the Seas (스컬지 오브 더 시즈)", "Flask of Brimstone / Flask of Venom (유황 플라스크 / 맹독 플라스크)"],
            "armor": ["Umbraphile Hood + Umbraphile Regalia + Umbraphile Boots", "Reaver Visage + Reaver Scale Mail + Reaver Cuisses"],
            "accessories": ["Asgard's Valor / Master Ninja Gear", "Angel Treads / Fairy Boots", "Eye of the Golem"],
            "next_goal": "Moon Lord 직전 stealth 중심 최종 하드모드 세팅 완성",
        },
    },
    "moon_lord": {
        "__meta__": {
            "stage": "Post-Moon Lord / Pre-Providence",
            "source_note": "Calamity Guide:Class setups/Post-Moon_Lord + Armor progression/Post-Moon_Lord",
        },
        "melee": {
            "weapons": ["Ark of the Elements (원소의 방주)", "Ark of the Cosmos (우주의 방주)"],
            "armor": ["Solar Flare Helmet + Solar Flare Breastplate + Solar Flare Leggings", "Tarragon Helm + Tarragon Breastplate + Tarragon Leggings"],
            "accessories": ["Asgard's Valor / Statis' Ninja Belt", "Warbanner of the Righteous", "Sand Shark Tooth Necklace"],
            "next_goal": "Providence / Storm Weaver 진행 후 Tarragon/Bloodflare 단계 진입",
        },
        "ranged": {
            "weapons": ["Prideful Hunter's Planar Ripper (플래너 리퍼)"],
            "armor": ["Vortex Helmet + Vortex Breastplate + Vortex Leggings", "Tarragon Visage + Tarragon Breastplate + Tarragon Leggings"],
            "accessories": ["Asgard's Valor / Statis' Ninja Belt", "Warbanner of the Righteous", "Sand Shark Tooth Necklace"],
            "next_goal": "Polterghast 이후 Bloodflare 또는 God Slayer 준비",
        },
        "mage": {
            "weapons": ["Triactis' True Paladinian Mage-Hammer of Might (트라이액티스의 진정한 팔라딘 마법망치)"],
            "armor": ["Nebula Helmet + Nebula Breastplate + Nebula Leggings", "Prismatic armor"],
            "accessories": ["Asgard's Valor / Statis' Ninja Belt", "Warbanner of the Righteous", "Bloodfin / Supreme Healing Potions"],
            "next_goal": "DoG 이후 Silva 중심으로 전환",
        },
        "summoner": {
            "weapons": ["King of Constellations, Tenryu (성좌의 왕 텐류)"],
            "armor": ["Stardust Helmet + Stardust Plate + Stardust Leggings", "Silva Horned Hood + Silva Armor + Silva Leggings"],
            "accessories": ["Asgard's Valor / Statis' Ninja Belt", "Heart of the Elements", "Bloodfin / Supreme Healing Potions"],
            "next_goal": "Yharon 이후 Auric Tesla로 최종 전환",
        },
        "rogue": {
            "weapons": ["The Dance of Light (빛의 춤)", "Ark of the Cosmos (우주의 방주)"],
            "armor": ["Empyrean Mask + Empyrean Cloak + Empyrean Cuisses", "God Slayer Mask + God Slayer Chestplate + God Slayer Leggings"],
            "accessories": ["Asgard's Valor / Statis' Ninja Belt", "Warbanner of the Righteous", "Chalice of the Blood God"],
            "next_goal": "Exo Mechs / Supreme Witch, Calamitas 전투 준비",
        },
    },
}

# Use source-validated dataset as runtime default.
POST_BOSS_LOADOUTS = SOURCE_VALIDATED_POST_BOSS_LOADOUTS


TERRARIA_SOURCE_URLS = [
    "https://calamitymod.wiki.gg/wiki/Guide:Class_setups",
    "https://calamitymod.wiki.gg/wiki/Bosses",
    "https://terraria.wiki.gg/wiki/Guide:Class_setups",
    "https://terraria.wiki.gg/wiki/Bosses",
]


TERRARIA_SOURCE_NOTES = {
    "desert_scourge": "Calamity 초반 프리-하드모드 클래스 셋업 구간",
    "crabulon": "Calamity 초반 프리-하드모드 클래스 셋업 구간",
    "hive_mind": "Calamity 초반 프리-하드모드 클래스 셋업 구간",
    "perforators": "Calamity 초반 프리-하드모드 클래스 셋업 구간",
    "slime_god": "Calamity 프리-하드모드 후반 클래스 셋업 구간",
    "wall_of_flesh": "하드모드 진입 직후 클래스 셋업 구간",
    "cryogen": "초중반 하드모드 클래스 셋업 구간",
    "plantera": "포스트-플랜테라 클래스 셋업 구간",
    "moon_lord": "포스트-문로드 클래스 셋업 구간",
}


ITEM_LOCALIZATION_MAP = {
    "Victide Shellmet": "빅타이드 쉘멧",
    "Victide Breastplate": "빅타이드 흉갑",
    "Victide Greaves": "빅타이드 경갑",
    "Victide Coral Turban": "빅타이드 코랄 터번",
    "Victide Hermit Helmet": "빅타이드 허밋 헬멧",
    "Victide Mask": "빅타이드 마스크",
    "Victide Headcrab": "빅타이드 헤드크랩",
    "Wulfrum Hat & Goggles": "울프럼 모자&고글",
    "Wulfrum Jacket": "울프럼 재킷",
    "Wulfrum Overalls": "울프럼 오버롤",
    "Statigel Helm": "스태티젤 헬멧",
    "Statigel Armor": "스태티젤 아머",
    "Statigel Greaves": "스태티젤 경갑",
    "Statigel Headgear": "스태티젤 헤드기어",
    "Statigel Cap": "스태티젤 캡",
    "Statigel Hood": "스태티젤 후드",
    "Statigel Mask": "스태티젤 마스크",
    "Molten Helmet": "몰튼 헬멧",
    "Molten Breastplate": "몰튼 흉갑",
    "Molten Greaves": "몰튼 경갑",
    "Mollusk Shellplate": "몰러스크 셸플레이트",
    "Mollusk Shelleggings": "몰러스크 셸레깅스",
    "Spider Mask": "스파이더 마스크",
    "Spider Breastplate": "스파이더 흉갑",
    "Spider Greaves": "스파이더 경갑",
    "Titan Heart Mask": "타이탄 하트 마스크",
    "Titan Heart Mantle": "타이탄 하트 맨틀",
    "Titan Heart Boots": "타이탄 하트 부츠",
    "Daedalus Mask": "다이달루스 마스크",
    "Daedalus Breastplate": "다이달루스 흉갑",
    "Daedalus Leggings": "다이달루스 레깅스",
    "Daedalus Facemask": "다이달루스 페이스마스크",
    "Reaver Helm": "리버 헬름",
    "Reaver Scale Mail": "리버 스케일 메일",
    "Reaver Cuisses": "리버 퀴스",
    "Reaver Visage": "리버 비사지",
    "Umbraphile Hood": "엄브라파일 후드",
    "Umbraphile Regalia": "엄브라파일 레갈리아",
    "Umbraphile Boots": "엄브라파일 부츠",
    "Spooky Helmet": "스푸키 헬멧",
    "Spooky Breastplate": "스푸키 흉갑",
    "Spooky Leggings": "스푸키 레깅스",
    "Plaguebringer Visor": "플레이그브링어 바이저",
    "Plaguebringer Carapace": "플레이그브링어 카라페이스",
    "Plaguebringer Pistons": "플레이그브링어 피스톤",
    "Hydrothermic armor": "하이드로써믹 아머",
    "Chlorophyte armor": "클로로파이트 아머",
    "Brimflame armor": "브림플레임 아머",
    "Spectre armor": "스펙터 아머",
    "Solar Flare Helmet": "솔라 플레어 헬멧",
    "Solar Flare Breastplate": "솔라 플레어 흉갑",
    "Solar Flare Leggings": "솔라 플레어 레깅스",
    "Tarragon Helm": "타라곤 헬름",
    "Tarragon Breastplate": "타라곤 흉갑",
    "Tarragon Leggings": "타라곤 레깅스",
    "Tarragon Visage": "타라곤 비사지",
    "Nebula Helmet": "네뷸라 헬멧",
    "Nebula Breastplate": "네뷸라 흉갑",
    "Nebula Leggings": "네뷸라 레깅스",
    "Vortex Helmet": "보텍스 헬멧",
    "Vortex Breastplate": "보텍스 흉갑",
    "Vortex Leggings": "보텍스 레깅스",
    "Stardust Helmet": "스타더스트 헬멧",
    "Stardust Plate": "스타더스트 플레이트",
    "Stardust Leggings": "스타더스트 레깅스",
    "Silva Horned Hood": "실바 혼드 후드",
    "Silva Armor": "실바 아머",
    "Silva Leggings": "실바 레깅스",
    "Empyrean Mask": "엠피리언 마스크",
    "Empyrean Cloak": "엠피리언 클록",
    "Empyrean Cuisses": "엠피리언 퀴스",
    "God Slayer Mask": "갓 슬레이어 마스크",
    "God Slayer Chestplate": "갓 슬레이어 흉갑",
    "God Slayer Leggings": "갓 슬레이어 레깅스",
    "Bundle of Horseshoe Balloons": "말굽 풍선 묶음",
    "Unholy Tonic": "언홀리 토닉",
    "Vicious Tonic": "비셔스 토닉",
    "Healing Potions": "치유 포션",
    "Strange Brew": "기묘한 물약",
    "Mana Flower": "마나 플라워",
    "Magic Cuffs": "매직 커프스",
    "Musket Ball": "머스킷 탄환",
    "Tungsten Bullet": "텅스텐 탄환",
    "Musket Balls": "머스킷 탄환",
    "Tungsten Bullets": "텅스텐 탄환",
    "Crown Jewel": "크라운 주얼",
    "Honey Dew": "허니 듀",
    "Honeyfins": "허니핀",
    "Restoration Potions": "회복 포션",
    "Counter Scarf": "카운터 스카프",
    "Deep Diver": "딥 다이버",
    "Fairy Boots": "페어리 부츠",
    "Terraspark Boots": "테라스파크 부츠",
    "Honey Dew / Radiant Ooze": "허니 듀 / 레이디언트 우즈",
    "Radiant Ooze": "레이디언트 우즈",
    "Cursed": "저주",
    "Ichor": "아이코르",
    "Evasion Scarf": "회피 스카프",
    "Ornate Shield": "오네이트 실드",
    "Ichor Bullets": "아이코르 탄환",
    "Cursed Bullets": "저주 탄환",
    "Asgard's Valor": "아스가르드의 용맹",
    "Master Ninja Gear": "마스터 닌자 장비",
    "Angel Treads": "엔젤 트레드",
    "Sand Shark Tooth Necklace": "샌드 샤크 이빨 목걸이",
    "Eye of the Golem": "골렘의 눈",
    "Statis' Ninja Belt": "스타티스의 닌자 벨트",
    "Warbanner of the Righteous": "의인의 전투기",
    "Bloodfin": "블러드핀",
    "Supreme Healing Potions": "상급 치유 포션",
    "Heart of the Elements": "원소의 심장",
    "Chalice of the Blood God": "피의 신의 성배",
}


def localize_terraria_item_text(text: str) -> str:
    """Append Korean labels to known item names in a free-form string."""
    if not text:
        return text

    if "(" in text and ")" in text:
        return text

    # Split while preserving delimiters used in this dataset.
    parts = re.split(r"(\s/\s|\s\+\s)", text)
    localized_parts = []
    for part in parts:
        if part in {" / ", " + "}:
            localized_parts.append(part)
            continue

        name = part.strip()
        ko = ITEM_LOCALIZATION_MAP.get(name)
        if ko:
            localized_parts.append(f"{name} ({ko})")
        else:
            localized_parts.append(part)

    return "".join(localized_parts)


def build_terraria_grounded_prompt(
    boss_key: str,
    class_key: str,
    boss_display: str,
    class_display: str,
    base_loadout: dict,
    source_note: str = "",
    source_stage: str = "",
) -> str:
    """Build a grounded prompt for Gemini using known source URLs."""
    weapons = ", ".join(base_loadout.get("weapons", [])) or "없음"
    armor = ", ".join(base_loadout.get("armor", [])) or "없음"
    accessories = ", ".join(base_loadout.get("accessories", [])) or "없음"
    next_goal = base_loadout.get("next_goal", "없음")
    resolved_note = source_note or TERRARIA_SOURCE_NOTES.get(boss_key, "Calamity 클래스 셋업 일반 구간")
    resolved_stage = source_stage or "미지정"
    source_urls = "\n".join(f"- {url}" for url in TERRARIA_SOURCE_URLS)

    return f"""너는 Terraria Calamity 세팅 가이드 검수자다.
아래 출처 범위를 기준으로만 답하고, 확신이 낮은 항목은 '검증 필요'라고 표시해라.

[입력]
- 보스: {boss_display} ({boss_key})
- 직업: {class_display} ({class_key})
- 기준 단계: {resolved_stage}
- 기준 메모: {resolved_note}

[초안 데이터]
- 무기: {weapons}
- 방어구: {armor}
- 악세사리: {accessories}
- 다음 목표: {next_goal}

[허용 출처]
{source_urls}

[출력 형식]
다음 형식을 지켜라.
1) 무기: 콤마로 2~4개
2) 방어구: 1~2개
3) 악세사리: 콤마로 3~5개
4) 다음 목표: 한 줄
5) 검증 메모: 한 줄

한국어로 간결하게 작성해라.
"""


def build_terraria_material_prompt(material_query: str, known_hint: Optional[dict] = None) -> str:
    """Build a grounded prompt to explain recipe/how-to-get for a material."""
    hint_text = ""
    if known_hint:
        hint_text = (
            f"- 이름: {known_hint.get('name', '')}\n"
            f"- 조합/제작(초안): {known_hint.get('recipe', '')}\n"
            f"- 획득처(초안): {known_hint.get('how_to_get', '')}\n"
            f"- 팁(초안): {known_hint.get('tips', '')}\n"
        )

    source_urls = "\n".join(f"- {url}" for url in TERRARIA_SOURCE_URLS)
    return f"""너는 Terraria + Calamity 재료 가이드 봇이다.
사용자가 입력한 재료의 조합법/획득처를 한국어로 설명해라.
확신이 낮은 정보는 반드시 '검증 필요'라고 명시해라.
존재하지 않거나 모호한 재료면 유사 후보를 2~4개 제시해라.

[사용자 입력 재료]
{material_query}

[내부 힌트 데이터]
{hint_text if hint_text else "- (없음)"}

[허용 출처]
{source_urls}

[출력 형식]
1) 재료명: 한 줄
2) 조합/제작: 한 줄~두 줄
3) 획득 방법: 한 줄~두 줄
4) 진행 팁: 한 줄
5) 검증 메모: 한 줄
"""
