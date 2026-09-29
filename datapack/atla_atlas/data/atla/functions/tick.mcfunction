scoreboard players enable @a atla_tp
scoreboard players enable @a atla_atlas
execute as @a[tag=!atla_has_atlas] run function atla:give_atlas
execute as @a[scores={atla_atlas=1..}] run function atla:give_atlas
execute as @a[scores={atla_tp=1..}] at @s run function atla:tp/go
