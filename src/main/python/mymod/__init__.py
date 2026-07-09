# Import all submodules here so they are registered when the mod loads
from . import items

# Export the mod_instance so the entrypoint in fabric.mod.json can find it
from .main import mod_instance
