import os
import datetime
import json
from tkinter import *
from urllib.request import urlopen
import webbrowser

import folium
import pandas as pd
import geopandas as gpd
from tkcalendar import *

pd.set_option('display.max_columns', None)
pd.set_option('display.max_colwidth', None)
pd.set_option('display.max_rows', None)


class Bookings(object):
    def __init__(self, booking_data):
        self.df = pd.DataFrame(pd.json_normalize(booking_data))
        self.reformat_timestamps()
        self.split_positions()
        self.clean_df()

    def reformat_timestamps(self):
        """Reformat the time stamps for the start and end of the bookings from epoch time to a pandas DateTime object
        in ISO 8601"""
        self.df.insert(loc=1, column="date", value=pd.to_datetime(self.df["start"], unit="s").dt.date)
        self.df["start"] = pd.to_datetime(self.df["start"], unit="s").dt.time
        self.df["end"] = pd.to_datetime(self.df["end"], unit="s").dt.time

    def split_positions(self):
        self.df.insert(loc=0, column="airport", value=self.df["position"].str.split("_").str[0])
        self.df["position"] = self.df["position"].str.split("_", n=1).str[1]

    def clean_df(self):
        """Remove unnecessary columns "vatsimid", "name" and "added" """
        self.df.drop(columns=["vatsimid", "name", "added"], inplace=True)


class Airports(object):
    def __init__(self, path):
        # TODO: Fix hard-coded row parsing
        self.df = pd.read_csv(path, skiprows=329, nrows=(17797 - 330), sep="|").rename(
            columns={";ICAO": "ICAO", "Latitude Decimal": "LAT", "Longitude Decimal": "LONG"})[
            ["ICAO", "LAT", "LONG", "IATA/LID", "FIR"]]


class FIRs(object):
    def __init__(self, fir_data_path, fir_boundaries_path):
        # TODO: Fix hard-coded row parsing
        self.fir_info = pd.read_csv(fir_data_path, skiprows=17799, nrows=(18441 - 17800), sep="|").rename(
            columns={";ICAO": "ICAO"})
        self.fir_boundaries = gpd.read_file(fir_boundaries_path)


class DatePicker(object):
    def __init__(self):
        self.date = None
        self.root = None
        self.cal = None
        self.picked_date = None
        self.display_date_picker()

    def grad_date(self):
        self.date.config(text="Selected Date is: " + self.cal.get_date())
        self.root.quit()

    def display_date_picker(self):
        # Create Object
        self.root = Tk()

        # Set geometry
        self.root.geometry("400x400")

        # Add Calendar
        self.cal = Calendar(self.root, selectmode='day', date=datetime.date.today())

        self.cal.pack(pady=20)

        # Add Button and Label
        Button(self.root, text="Get Date", command=self.grad_date).pack(pady=20)

        self.date = Label(self.root, text="")
        self.date.pack(pady=20)

        # Execute Tkinter
        self.root.mainloop()

        self.picked_date = self.cal.selection_get()


class Map(object):
    def __init__(self, filtered_bookings, airports, fir_information, fir_boundaries):
        self.map = folium.Map(location=(51.250982119671754, 10.489567530592556), zoom_start=6)
        self.filtered_bookings = filtered_bookings
        self.airports = airports
        self.fir_information = fir_information
        self.fir_boundaries = fir_boundaries
        self.fir_idents = []
        self.style = {'fillColor': '#f5532f80', 'color': '#ff213680'}
        self.set_marker = False

        self.populate_map()
        self.draw()

    def populate_map(self):
        online_airports = self.filtered_bookings["airport"].unique()
        for icao in online_airports:
            self.set_marker = False
            airport_code = self.airports["ICAO"]
            alt_airport_callsign = self.airports["IATA/LID"]
            pos = self.filtered_bookings.loc[self.filtered_bookings["airport"] == icao, "position"]
            pos_time = self.filtered_bookings.loc[self.filtered_bookings["airport"] == icao,
                       "position":"end"]  # .to_string(index=False)
            pos_time_html = pos_time.to_html(index=False)
            # popup_text = ' '.join(map(str, pos.values))
            # popup_text = pos_time
            iframe = folium.IFrame(html=pos_time_html, width=300, height=300)
            popup_text = folium.Popup(iframe, max_width=2650, parse_html=True)
            # Station ID is an airport and has the normal ICAO identifier
            if airport_code.str.match(icao).any():
                lat = self.airports.loc[self.airports["ICAO"] == icao, "LAT"].item()
                long = self.airports.loc[self.airports["ICAO"] == icao, "LONG"].item()
                if pos.str.contains("DEL|GND|TWR").any():
                    folium.Marker(location=(lat, long), popup=popup_text, tooltip=icao).add_to(self.map)
                    self.set_marker = True
                if pos.str.contains("APP").any():
                    if not self.set_marker:
                        folium.Marker(location=(lat, long), popup=popup_text, tooltip=icao).add_to(self.map)
                    folium.CircleMarker(location=(lat, long), radius=25, color="#3186cc", fill=True,
                                        fill_color="#3186cc", tooltip=icao).add_to(self.map)
            # Station ID is an alternate callsign (thanks for nothing, UK)
            elif alt_airport_callsign.str.match(icao).any():
                lat = self.airports.loc[self.airports["IATA/LID"] == icao, "LAT"].item()
                long = self.airports.loc[self.airports["IATA/LID"] == icao, "LONG"].item()
                if pos.str.contains("DEL|GND|TWR").any():
                    folium.Marker(location=(lat, long), popup=popup_text, tooltip=icao).add_to(self.map)
                    self.set_marker = True
                if pos.str.contains("APP").any():
                    if not self.set_marker:
                        folium.Marker(location=(lat, long), popup=popup_text, tooltip=icao).add_to(self.map)
                    folium.CircleMarker(location=(lat, long), radius=25, color="#3186cc", fill=True,
                                        fill_color="#3186cc", tooltip=icao).add_to(self.map)
            # Station ID is an FIR identifier
            else:
                fir_ids = (icao + "-" + pos)
                for fir_id in fir_ids:
                    if "_" in fir_id:
                        fir_id_formatted = fir_id.split("_")[0]
                    else:
                        fir_id_formatted = fir_id.split("-")[0]
                    # The FIR identifier matches in the GeoJSON db
                    if self.fir_boundaries["id"].str.match(fir_id_formatted).any():
                        bnd_polygon = self.fir_boundaries.loc[self.fir_boundaries["id"] == fir_id_formatted, "geometry"]
                        folium.GeoJson(bnd_polygon, tooltip=fir_id_formatted,
                                       style_function=lambda x: self.style).add_to(self.map)
                    # No exact match in GeoJSON boundary database --> Map the callsign prefix to the corresponding FIR id
                    else:
                        fir_csp = "_".join(fir_id_formatted.split("-")[:2])
                        fir_id_alt = self.fir_information.loc[
                            self.fir_information["CALLSIGN PREFIX"] == fir_csp, "FIR BOUNDARY"].item()
                        bnd_polygon = self.fir_boundaries.loc[self.fir_boundaries["id"] == fir_id_alt, "geometry"]
                        folium.GeoJson(bnd_polygon, tooltip=fir_csp, style_function=lambda x: self.style).add_to(
                            self.map)

    def draw(self):
        self.map.save("vatsimBookingMap.html")


if __name__ == "__main__":
    # Get booking data from statsim
    data = urlopen("https://statsim.net/atc/?json=true")
    data_json = json.loads(data.read().decode())

    # Load booking data
    bookings_df = Bookings(data_json).df
    bookings_df.to_html(".\\debug\\bookings.html")

    # Load aiport coordinate data
    airports_df = Airports(".\\db\\VATSpy.dat").df

    # Load FIR data
    fir_data = FIRs(".\\db\\VATSpy.dat", ".\\db\\Boundaries.geojson")
    fir_info = fir_data.fir_info
    fir_bounds = fir_data.fir_boundaries

    # Pick the date and filter the data
    date_picker = DatePicker()

    desired_date = pd.Timestamp(date_picker.picked_date).date()
    desired_time = pd.Timestamp(2023, 5, 3, 18, 0, 0).time()

    desired_bookings_df = bookings_df[(bookings_df["date"] == desired_date) & (bookings_df["start"] <= desired_time) & (
            desired_time < bookings_df["end"])]
    desired_bookings_df = desired_bookings_df.sort_values("airport")

    # Display the map
    booking_map = Map(desired_bookings_df, airports_df, fir_info, fir_bounds)
    booking_map.draw()

    desired_bookings_df = desired_bookings_df.style.set_caption(
        "\n=== Stations booked on {} at {} ===\n\nFIR identifiers: \n\n{}".format(desired_date.strftime("%Y-%m-%d"),
                                                                                  desired_time.strftime('%X'), ' '.join(
                map(str, booking_map.fir_idents))))
    desired_bookings_df.to_html("desired_bookings.html", index_names=False)

    chrome_path = "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe %s"
    bookings_save_path = "file:///{}/desired_bookings.html".format(os.getcwd())
    map_save_path = "file:///{}/vatsimBookingMap.html".format(os.getcwd())

    webbrowser.get(chrome_path).open(bookings_save_path)

    webbrowser.get(chrome_path).open_new_tab(map_save_path)
