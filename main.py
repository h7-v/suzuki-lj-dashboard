import sys
from PyQt5.QtWidgets import *
from PyQt5 import uic


class GUI(QMainWindow):

    def __init__(self):
        super(GUI, self).__init__()
        uic.loadUi("mainwindow.ui", self)
        self.show()

        self.testButton.clicked.connect(self.button_clicked)


    def button_clicked(self):
        print("Clicked")


def main():
    app = QApplication([])
    window = GUI()
    app.exec_()


if __name__ == "__main__":
    main()