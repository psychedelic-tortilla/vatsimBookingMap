from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWebEngineWidgets import *
from PyQt5.QtWidgets import *
from PyQt5 import uic

import sys
import os

from vbMapLib import *


class vatsimBookingMapWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.vat_map = None
        self.renderer = None

        self.ui = uic.loadUi("{}/vatsimBookingMap.ui".format(os.getcwd()))
        self.setupUi()

    def setupUi(self):
        self.ui.dateTimeEdit.setDate(QDate.currentDate())
        self.ui.dateTimeEdit.setTime(QTime(18, 0, 0))
        self.ui.tabWidget.setCurrentIndex(0)

        self.ui.applyDateBtn.clicked.connect(lambda: self.draw_map())
        self.draw_map()
        self.render_events_page()

    def draw_map(self):
        self.init_vatsimMap()
        self.ui.mapWidget.setHtml(self.vat_map.get_root().render())
        self.render_booking_dataframe()

    def init_vatsimMap(self):
        statsim_url = "https://statsim.net/atc/?json=true"
        vatspy_data = "{}/db/VATSpy.dat".format(os.getcwd())
        fir_boundary_data = "{}/db/Boundaries.geojson".format(os.getcwd())

        timestamp = self.ui.dateTimeEdit.dateTime().toPyDateTime()
        desired_timestamp = pd.Timestamp(timestamp)

        self.renderer = Renderer(bookings_url=statsim_url, vatspy_path=vatspy_data, boundaries_path=fir_boundary_data)
        self.renderer.render(timestamp=desired_timestamp)
        self.vat_map = self.renderer.get_map()

    def render_booking_dataframe(self):
        df = self.renderer.get_desired_bookings()
        df_html = df.to_html(index=False)
        self.ui.bookingDfWidget.setHtml(df_html)

    def render_events_page(self):
        self.ui.eventsTodayWidget.page().profile().setHttpUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36")
        self.ui.eventsTodayWidget.load(QUrl("https://aviation.allanville.com/vatsim/events"))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = vatsimBookingMapWidget().ui
    window.showMaximized()
    sys.exit(app.exec())
