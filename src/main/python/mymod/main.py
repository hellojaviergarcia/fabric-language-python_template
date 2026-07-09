from net.fabricmc.api import ModInitializer
from org.slf4j import LoggerFactory

# Use the mod ID as the logger name
logger = LoggerFactory.getLogger("mymod")

class MyMod(ModInitializer):
    def onInitialize(self):
        logger.info("Hello from Python! The template mod has initialized successfully.")

# The adapter will find this instance and use it as the main entrypoint
mod_instance = MyMod()
