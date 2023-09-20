# Get information about BT device player0 or fd0 using
# dbus-monitor --system "type='signal',sender='org.bluez'"
# player0 and fd0 may have values other than 0. This is handled
# appropriately.

# TODO: If Status becomes stopped from MediaPlayer1, clear the song label
# TODO: Perhaps if there is a way to request what the current song it on
# dbus then we should probably do that. Currently if the Bluetooth device
# is connected but doesn't have a player active then no song is displayed.
# This is fine but becomes a problem when Spotify if then opened, a song is
# played but only an active of playing status is passed with no song info.

import subprocess
import time
from PyQt5.QtCore import Qt, QTimer, QRect
from PyQt5.QtGui import QPainter, QFontMetrics
from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QVBoxLayout
from PyQt5 import uic
from PyQt5.QtCore import QThread
from PyQt5.QtCore import pyqtSignal
from pydbus import SystemBus
from gi.repository import GLib
from functools import partial


def get_connected_bluetooth_mac(bus_object, window):
    bluez_service = bus_object.get('org.bluez', '/')
    managed_objects = bluez_service.GetManagedObjects()

    # Loop through all managed objects to find connected device
    for path, interfaces in managed_objects.items():
        if 'org.bluez.Device1' in interfaces:
            device = bus_object.get('org.bluez', path)

            device.PropertiesChanged.connect(partial(
                on_device_property_changed, window))

            device_properties = managed_objects[path]['org.bluez.Device1']
            if 'Connected' in device_properties and \
               device_properties['Connected']:
                return path.split('/')[-1]  # Extract MAC address from the path

    return None  # Return None if no connected device is found


# Used to handle connections and disconnections of Bluetooth devices.
def on_device_property_changed(window, *args, **kwargs):
    # print("All args:", args)  # Debugging line
    # print("All kwargs:", kwargs)  # Debugging line

    interface_name = args[0]
    properties = args[1]

    # print(f"Interface: {interface_name}")  # Debugging line
    # print(f"Properties: {properties}")  # Debugging line

    try:
        if interface_name == 'org.bluez.Device1':
            if 'Connected' in properties:
                is_connected = properties['Connected']
                if is_connected:
                    print("A Bluetooth device has connected.")
                    # You can add your logic here to handle the new connection
                    window.handle_new_connection()
                else:
                    print("A Bluetooth device has disconnected.")
                    # You can add your logic here to handle the disconnection
                    window.handle_disconnection()
    except Exception as e:
        print(f"An error occurred in on_device_property_changed: {e}")


# The dbus player path can change as devices are connected
# and disconnected. We cannot hardcode player0 as the path and must
# therefore retrive it once we have the device MAC address.
def find_media_player_path(bus_object, mac_address):
    bluez_service = bus_object.get('org.bluez', '/')
    managed_objects = bluez_service.GetManagedObjects()

    for path, interfaces in managed_objects.items():
        if 'org.bluez.MediaPlayer1' in interfaces:
            if mac_address.replace(":", "_").lower() in path.lower():
                return path
    return None


# Same thing as above except retrieving the path that deals with
# volume controls. Typically "fd" followed by a number.
def find_media_transport_path(bus_object, mac_address):
    bluez_service = bus_object.get('org.bluez', '/')
    managed_objects = bluez_service.GetManagedObjects()

    for path, interfaces in managed_objects.items():
        if 'org.bluez.MediaTransport1' in interfaces:
            if mac_address.replace(":", "_").lower() in path.lower():
                return path
    return None


# TODO: Depending on whether or not we also want to show album info
# consider switching out commented code.
def on_player_properties_change(window, *args, **kwargs):
    if window.ignore_properties_changed:
        return
    print("Media properties changed:", args, kwargs)

    # Extract track information from arguments
    track_info = args[1].get('Track', {})
    # print("Track info:", track_info)  # Debugging line

    # Check if track information is available
    if isinstance(track_info, dict):
        title = track_info.get('Title', "Unknown")
        # album = track_info.get('Album', "Unknown")
        artist = track_info.get('Artist', "Unknown")

        # Only emit the signal if at least one of the title, album,
        # or artist is known
        # if title != "Unknown" or album != "Unknown" or artist != "Unknown":
        if title != "Unknown" or artist != "Unknown":
            # song_info = f"{title} - {album} Artist: {artist}"
            song_info = f"{title} - {artist}     "
            window.trackChanged.emit(song_info)

    status_info = args[1].get('Status')
    if status_info:
        if status_info == "playing" or status_info == "paused":
            window.mediaPlayerStatusChanged.emit(status_info)


# Tracking volume changes to have a use for MediaTransport.
# MediaTransport is not used in practice currently but that may or may
# not change.
def on_transport_change(window, *args, **kwargs):
    print("Transport properties changed: ", args, kwargs)


class GLibThread(QThread):
    def run(self):
        loop = GLib.MainLoop()
        loop.run()


class ScrollingLabel(QWidget):
    def __init__(self, text, parent=None):
        super(ScrollingLabel, self).__init__(parent)
        self._text = text
        self._offset = 0

        # Set fixed width and height for the widget
        self.setFixedWidth(400)
        self.setFixedHeight(50)

        # Initialize timer for scrolling
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_offset)
        self._timer.start(16)  # Update every 16 ms (about 60 frames/second)

    def paintEvent(self, event):
        painter = QPainter(self)
        font_metrics = QFontMetrics(painter.font())
        text_width = font_metrics.width(self._text)

        if text_width > self.width():
            # Add a space at the end of the text for separation
            spaced_text = self._text + ' '
            spaced_text_width = font_metrics.width(spaced_text)

            # Calculate the x position to start drawing text
            x = int(self.width() - self._offset)

            # Draw text twice to create a continuous scrolling effect
            painter.drawText(
                QRect(x, 0, spaced_text_width, self.height()),
                Qt.AlignVCenter,
                spaced_text
            )
            painter.drawText(
                QRect(x - spaced_text_width, 0, spaced_text_width,
                      self.height()),
                Qt.AlignVCenter,
                spaced_text
            )
        else:
            # Center the text if it fits within the widget
            x = max((self.width() - text_width) // 2, 0)  # Ensure x is +tive
            painter.drawText(QRect(x, 0, self.width() - x, self.height()),
                             Qt.AlignVCenter, self._text)

            # Debug to check widget border size
            # painter.setPen(Qt.red)
            # painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def _update_offset(self):
        font_metrics = QFontMetrics(self.font())
        text_width = font_metrics.width(self._text)

        # Only scroll if the text width is greater than the widget width
        if text_width > self.width():
            self._offset += 0.5  # Change this value to adjust speed

            if self._offset > text_width:
                self._offset = 0
        else:
            self._offset = 0  # Reset offset if text fits within the widget

        self.update()  # Trigger a repaint

    def update_text(self, new_text):
        self._text = new_text
        self.update()


class GUI(QMainWindow):
    trackChanged = pyqtSignal(str)
    mediaPlayerStatusChanged = pyqtSignal(str)

    # Any changes made in __init__() must be reflected in
    # handle_new_connection(). See the note preceding this function.
    def __init__(self):
        super(GUI, self).__init__()
        uic.loadUi("mainwindow.ui", self)
        self.show()

        self.trackIsPlaying = False
        # We need a way of tracking how audio transport has changed,
        # whether that's on the bluetooth device end or if a button has been
        # pushed.
        self.playPauseInitiatedByButton = False
        self.playPauseButton.clicked.connect(self.playPauseButton_clicked)
        self.nextTrackButton.clicked.connect(self.nextTrackButton_clicked)
        self.prevTrackButton.clicked.connect(self.prevTrackButton_clicked)

        self.volDownButton.clicked.connect(self.volDownButton_clicked)
        self.volUpButton.clicked.connect(self.volUpButton_clicked)

        self.dbus_thread = GLibThread()
        self.trackChanged.connect(self.update_song_label)
        self.mediaPlayerStatusChanged.connect(self.handleMPStatusChange)

        self.scrolling_label = ScrollingLabel("Nothing playing")
        layout = QVBoxLayout()
        layout.addWidget(self.scrolling_label)

        self.scrollingLabelPlaceholder.setLayout(layout)

        # dbus init. Also found in handle_new_connection() below
        try:
            # Make dbus connection.
            self.bus = SystemBus()

            # Set the flag to process the PropertiesChanged signal.
            # Used in on_player_properties_change()
            self.ignore_properties_changed = False

            # Format: dev_XX_XX_XX_XX_XX_XX
            self.bt_mac_address = get_connected_bluetooth_mac(self.bus, self)

            if self.bt_mac_address:
                print(f"Bluetooth device MAC address: {self.bt_mac_address}")

                # Format: /org/bluez/hci0/dev_XX_XX_XX_XX_XX_XX/playerX
                player_device_path = find_media_player_path(
                    self.bus, self.bt_mac_address)
                print("Device player path: ", player_device_path)

                try:
                    if player_device_path:
                        # Connect to dbus media player
                        self.media_player = self.bus.get('org.bluez',
                                                         player_device_path)
                    else:
                        print("No player device path!")
                except Exception as e:
                    print(f"Couldn't get media player: {e}")
                    return

                other_player_properties = self.media_player.GetAll(
                    'org.bluez.MediaPlayer1')
                print("All media properties:", other_player_properties)

                # Get the current song information to display song information
                # on connect.
                current_track = self.media_player.Get('org.bluez.MediaPlayer1',
                                                      'Track')
                if current_track:
                    print("Initial track:", current_track)
                    self.update_label_with_track_info(current_track)

                # Listen for changes and call on_player_properties_change()
                self.media_player.PropertiesChanged.connect(partial(
                    on_player_properties_change, self))

                # Format: /org/bluez/hci0/dev_XX_XX_XX_XX_XX_XX/fdX
                transport_device_path = find_media_transport_path(
                    self.bus, self.bt_mac_address)
                print("Device transport path: ", transport_device_path)

                try:
                    if transport_device_path:
                        # Connect to dbus media transport
                        self.media_transport = self.bus.get(
                            'org.bluez', transport_device_path)
                    else:
                        print("No transport device path!")
                except Exception as e:
                    print(f"Couldn't get media transport: {e}")

                other_transport_properties = self.media_transport.GetAll(
                    'org.bluez.MediaTransport1')
                print("All transport properties:", other_transport_properties)

                current_state = self.media_transport.Get(
                    'org.bluez.MediaTransport1', 'State')

                if current_state:
                    print("Initial state:", current_state)
                    if current_state == "idle":
                        self.trackIsPlaying = False
                        self.playPauseButton.setText("|>")
                    elif current_state == "active":
                        self.trackIsPlaying = False
                        self.playPauseButton.setText("||")

                # This may not be used in the final build but we'll
                # set up volume anyway.
                self.media_transport.PropertiesChanged.connect(
                    partial(on_transport_change, self))

            else:
                print("No connected Bluetooth device found.")
                self.scrolling_label.update_text("No media device connected")

        except Exception as e:
            print(f"An error occurred in GUI constructor: {e}")

        # Now we are set up we can start the Bluetooth thread
        self.dbus_thread.start()

    # Used for handling any new Bluetooth connection after program init.
    # Despite the fact that this is pretty much completely repeated code
    # to what's found in __init__ there is an additional time.sleep(2)
    # below. If we run this on startup we have an unnecessary 2 second
    # increase in start time. Without waiting 2 seconds below a race condition
    # fails, and because this sleep() is nested I would prefer not to turn
    # this all into spaghetti. This function must be updated if changes are
    # made in __init__()
    # See above code for comments.
    def handle_new_connection(self):
        try:
            # Set the flag to process the PropertiesChanged signal
            self.ignore_properties_changed = False

            self.bt_mac_address = get_connected_bluetooth_mac(self.bus, self)
            if self.bt_mac_address:
                print(f"New Bluetooth device MAC address: "
                      f"{self.bt_mac_address}")
                time.sleep(2)  # Make sure the media player object is ready

                player_device_path = find_media_player_path(
                    self.bus, self.bt_mac_address)

                try:
                    if player_device_path:
                        self.media_player = self.bus.get('org.bluez',
                                                         player_device_path)
                    else:
                        print("No player device path!")
                except Exception as e:
                    print(f"Couldn't get media player: {e}")
                    return

                other_player_properties = self.media_player.GetAll(
                    'org.bluez.MediaPlayer1')
                print("All media properties:", other_player_properties)

                # Get the current song information
                current_track = self.media_player.Get('org.bluez.MediaPlayer1',
                                                      'Track')
                if current_track:
                    print("Initial track:", current_track)
                    self.update_label_with_track_info(current_track)

                self.media_player.PropertiesChanged.connect(partial(
                    on_player_properties_change, self))

                transport_device_path = find_media_transport_path(
                    self.bus, self.bt_mac_address)

                try:
                    if transport_device_path:
                        self.media_transport = self.bus.get(
                            'org.bluez', transport_device_path)
                    else:
                        print("No transport device path!")
                except Exception as e:
                    print(f"Couldn't get media transport: {e}")

                other_transport_properties = self.media_transport.GetAll(
                    'org.bluez.MediaTransport1')
                print("All transport properties:", other_transport_properties)

                current_state = self.media_transport.Get(
                    'org.bluez.MediaTransport1', 'State')

                if current_state:
                    print("Initial state:", current_state)
                    if current_state == "idle":
                        self.trackIsPlaying = False
                        self.playPauseButton.setText("|>")
                    elif current_state == "active":
                        self.trackIsPlaying = False
                        self.playPauseButton.setText("||")

                self.media_transport.PropertiesChanged.connect(
                    partial(on_transport_change, self))

            else:
                print("No connected Bluetooth device found.")
                self.scrolling_label.update_text("No media device connected")

        except Exception as e:
            print(f"An error occurred in handle_new_connection(): {e}")

    # According to dbus spec there is nothing we need to do with the bus
    # object(?)
    def handle_disconnection(self):
        try:
            # Set a flag to ignore the PropertiesChanged signal
            self.ignore_properties_changed = True

            # No track playing is no device connected
            self.trackIsPlaying = False

            # Reset UI elements
            self.scrolling_label.update_text("No media device connected")
            self.playPauseButton.setText("|>")

            # Reset any internal state variables
            self.bt_mac_address = None
            self.media_player = None
            self.media_transport = None

        except Exception as e:
            print(f"An error occurred in handle_disconnection(): {e}")

    def handleMPStatusChange(self, status_info):
        if status_info == "playing":
            self.trackIsPlaying = True
            self.playPauseButton.setText("||")
        elif status_info == "paused":
            self.trackIsPlaying = False
            self.playPauseButton.setText("|>")

    def update_label_with_track_info(self, track_info):
        song_info = "Unknown (waiting on device for info)"
        title = track_info.get('Title', "Unknown")
        album = track_info.get('Album', "Unknown")
        artist = track_info.get('Artist', "Unknown")

        if title == "" and album == "" and artist == "":
            song_info = "Device connected"
        elif title != "Unknown" or album != "Unknown" or artist != "Unknown":
            song_info = f"{title} - {artist}"

        self.trackChanged.emit(song_info)

    def update_song_label(self, new_song):
        self.scrolling_label.update_text(f"{new_song}")

    def playpause_track(self):
        if self.trackIsPlaying:
            try:
                self.media_player.Pause()
                print("Media pause command sent.")
            except Exception as e:
                print(f"Failed to send pause command: {e}")
        elif not self.trackIsPlaying:
            try:
                self.media_player.Play()
                print("Media play command sent.")
            except Exception as e:
                print(f"Failed to send play command: {e}")

    def playPauseButton_clicked(self):
        self.playPauseInitiatedByButton = True
        self.playpause_track()

    def nextTrackButton_clicked(self):
        try:
            self.media_player.Next()
            print("Next track command sent.")
        except Exception as e:
            print(f"Failed to send next track command: {e}")

    def prevTrackButton_clicked(self):
        try:
            self.media_player.Previous()
            print("Previous track command sent.")
        except Exception as e:
            print(f"Failed to send previous track command: {e}")

    def volDownButton_clicked(self):
        subprocess.run(["amixer", "set", "Master", "--", "5%-"])
        print("Volume decreased")

    def volUpButton_clicked(self):
        subprocess.run(["amixer", "set", "Master", "--", "5%+"])
        print("Volume increased")


def main():
    app = QApplication([])
    window = GUI()

    window.show()
    app.exec_()


if __name__ == "__main__":
    main()
