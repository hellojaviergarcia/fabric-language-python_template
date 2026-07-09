from minecraft_py import item
from minecraft_py.items import create_food

# A basic item
@item("mymod", "ruby")
def ruby():
    pass

# An item with usage logic and food properties
def on_berry_use(level, player, hand):
    print(f"{player.getName().getString()} ate a magic berry!")

magic_berry = create_food(
    "mymod", 
    "magic_berry", 
    nutrition=6, 
    saturation=1.2, 
    on_use=on_berry_use
)
