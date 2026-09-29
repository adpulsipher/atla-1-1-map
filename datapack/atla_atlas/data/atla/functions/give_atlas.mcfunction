loot give @s loot atla:atlas
tag @s add atla_has_atlas
scoreboard players set @s atla_atlas 0
tellraw @s {"text":"You carry the Atlas of the Four Nations - open it to travel. (/trigger atla_atlas for another copy)","color":"gold"}
