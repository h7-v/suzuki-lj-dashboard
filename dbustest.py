
from pydbus import SystemBus
from gi.repository import GLib

def on_track_change(*args, **kwargs):
    print("Track changed signal received.")
    print("Args:", args)
    print("Kwargs:", kwargs)
    print(type(args))
    print(type(kwargs))

try:
    bus = SystemBus()
    media_player = bus.get('org.bluez', '/org/bluez/hci0/dev_44_35_83_3E_0E_0A/player0')  # Replace with your device's MAC
    print("Connected to media player.")
    media_player.PropertiesChanged.connect(on_track_change)
except KeyError:
    print("Failed to connect to the media player. Make sure the device is connected and try again.")

loop = GLib.MainLoop()
loop.run()

