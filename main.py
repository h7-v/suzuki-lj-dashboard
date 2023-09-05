import subprocess
from PyQt5.QtCore import Qt, QTimer, QRect
from PyQt5.QtGui import QPainter, QFontMetrics
from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QVBoxLayout
from PyQt5 import uic
from PyQt5.QtCore import QThread
from PyQt5.QtCore import pyqtSignal
from pydbus import SystemBus
from gi.repository import GLib
from functools import partial


def on_track_change(window, *args, **kwargs):
    print("Track changed:", args, kwargs)

    # Check if 'Track' exists in the dictionary and if it itself
    # is a dictionary
    track_info = args[1].get('Track', {})
    print("Track info:", track_info)  # Debugging line

    if isinstance(track_info, dict):
        title = track_info.get('Title', "Unknown")
        album = track_info.get('Album', "Unknown")
        artist = track_info.get('Artist', "Unknown")

        # Only emit the signal if at least one of the title, album,
        # or artist is known
        if title != "Unknown" or album != "Unknown" or artist != "Unknown":
            # song_info = f"{title} - {album} Artist: {artist}"
            song_info = f"{title} - {artist}     "
            window.trackChanged.emit(song_info)


class GLibThread(QThread):
    # trackChanged = pyqtSignal(str)  # Define a new signal

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
        try:
            bus = SystemBus()

            media_player = bus.get('org.bluez',
                                   ('/org/bluez/hci0/dev_44_35_83_3E_0E_0A/'
                                    'player0')
                                   )  # Replace with your device's MAC

            media_player.PropertiesChanged.connect(partial(
                on_track_change, self))

        except KeyError:
            print("Failed to connect to the media player. "
                  "Make sure the device is connected and try again.")

        self.dbus_thread.start()

        self.scrolling_label = ScrollingLabel("Nothing playing")
        layout = QVBoxLayout()
        layout.addWidget(self.scrolling_label)

        self.scrollingLabelPlaceholder.setLayout(layout)

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
