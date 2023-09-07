# Get information about BT device player0 or fd0 using
# dbus-monitor --system "type='signal',sender='org.bluez'"
# Occasionally the object path /player0 is not available and /fd0 is used
# instead. The player does not function properly if this is the case.

# TODO: Check for the fd0 case and reset either the dbus connection
# of the bluetooth service.

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
    # print("All kwargs:", kwargs) # Debugging line

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


# TODO: Depending on whether or not we also want to show album info
# consider switching out commented code.
def on_track_change(window, *args, **kwargs):
    if window.ignore_properties_changed:
        return
    print("Track changed:", args, kwargs)

    # Extract track information from arguments
    track_info = args[1].get('Track', {})
    print("Track info:", track_info)  # Debugging line

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

    def __init__(self):
        super(GUI, self).__init__()
        uic.loadUi("mainwindow.ui", self)
        self.show()

        self.volDownButton.clicked.connect(self.volDownButton_clicked)
        self.volUpButton.clicked.connect(self.volUpButton_clicked)

        self.dbus_thread = GLibThread()
        self.trackChanged.connect(self.update_song_label)

        self.scrolling_label = ScrollingLabel("Nothing playing")
        layout = QVBoxLayout()
        layout.addWidget(self.scrolling_label)

        self.scrollingLabelPlaceholder.setLayout(layout)

        try:
            self.bus = SystemBus()

            # Set the flag to process the PropertiesChanged signal
            self.ignore_properties_changed = False

            self.bt_mac_address = get_connected_bluetooth_mac(self.bus, self)

            if self.bt_mac_address:
                print(f"Bluetooth device MAC address: {self.bt_mac_address}")
                device_path = (f'/org/bluez/hci0/'
                               f'{self.bt_mac_address.replace(":", "_")}'
                               f'/player0')

                print("dpath", device_path)

                try:
                    self.media_player = self.bus.get('org.bluez', device_path)
                except Exception as e:
                    print(f"Couldn't get media player: {e}")
                    return

                other_properties = self.media_player.GetAll('org.bluez'
                                                            '.MediaPlayer1')
                print("All properties:", other_properties)

                # Get the current song information
                current_track = self.media_player.Get('org.bluez.MediaPlayer1',
                                                      'Track')
                if current_track:
                    print("Initial track:", current_track)
                    self.update_label_with_track_info(current_track)

                self.media_player.PropertiesChanged.connect(partial(
                    on_track_change, self))

            else:
                print("No connected Bluetooth device found.")
                self.scrolling_label.update_text("No media device connected")

        except Exception as e:
            print(f"An error occurred in GUI constructor: {e}")

        self.dbus_thread.start()

    def handle_new_connection(self):
        try:
            # Set the flag to process the PropertiesChanged signal
            self.ignore_properties_changed = False

            self.bt_mac_address = get_connected_bluetooth_mac(self.bus, self)
            if self.bt_mac_address:
                print(f"New Bluetooth device MAC address: "
                      f"{self.bt_mac_address}")
                time.sleep(2)  # Make sure the media player object is ready
                device_path = (f'/org/bluez/hci0/'
                               f'{self.bt_mac_address.replace(":", "_")}'
                               f'/player0')

                self.media_player = self.bus.get('org.bluez', device_path)

                # Get the current song information
                current_track = self.media_player.Get('org.bluez.MediaPlayer1',
                                                      'Track')
                if current_track:
                    print("Initial track:", current_track)
                    self.update_label_with_track_info(current_track)

                self.media_player.PropertiesChanged.connect(partial(
                    on_track_change, self))
            else:
                print("No connected Bluetooth device found.")
                self.scrolling_label.update_text("No media device connected")
        except Exception as e:
            print(f"An error occurred in handle_new_connection(): {e}")

    def handle_disconnection(self):
        try:
            # Set a flag to ignore the PropertiesChanged signal
            self.ignore_properties_changed = True

            # Reset UI elements
            self.scrolling_label.update_text("No media device connected")

            # Reset any internal state variables
            self.bt_mac_address = None
            self.media_player = None

        except Exception as e:
            print(f"An error occurred in handle_disconnection(): {e}")

    def update_label_with_track_info(self, track_info):
        title = track_info.get('Title', "Unknown")
        album = track_info.get('Album', "Unknown")
        artist = track_info.get('Artist', "Unknown")

        if title != "Unknown" or album != "Unknown" or artist != "Unknown":
            song_info = f"{title} - {artist}     "
            self.trackChanged.emit(song_info)

    def update_song_label(self, new_song):
        self.scrolling_label.update_text(f"{new_song}")

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
