"""Builder name -> function registry."""
from . import air, basingse, earth, fire, water

BUILDERS = {
    "southern_water_tribe": water.southern_water_tribe,
    "northern_water_tribe": water.northern_water_tribe,
    "southern_air_temple": air.southern_air_temple,
    "northern_air_temple": air.northern_air_temple,
    "eastern_air_temple": air.eastern_air_temple,
    "western_air_temple": air.western_air_temple,
    "foggy_swamp": earth.foggy_swamp,
    "kyoshi_island": earth.kyoshi_island,
    "omashu": earth.omashu,
    "senlin_village": earth.senlin_village,
    "great_divide": earth.great_divide,
    "gaoling": earth.gaoling,
    "serpents_pass": earth.serpents_pass,
    "full_moon_bay": earth.full_moon_bay,
    "wan_shi_tong_library": earth.wan_shi_tong_library,
    "misty_palms_oasis": earth.misty_palms_oasis,
    "si_wong_rock": earth.si_wong_rock,
    "wulong_forest": earth.wulong_forest,
    "ba_sing_se": basingse.ba_sing_se,
    "crescent_island": fire.crescent_island,
    "sun_warriors": fire.sun_warriors,
    "boiling_rock": fire.boiling_rock,
    "ember_island": fire.ember_island,
    "fire_nation_capital": fire.fire_nation_capital,
}
