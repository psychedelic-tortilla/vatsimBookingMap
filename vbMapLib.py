import datetime
import json
import os
from urllib.request import urlopen

import folium
from folium import plugins
import geopandas as gpd
import pandas as pd


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


class Map(object):
    def __init__(self, filtered_bookings, airports, fir_information, fir_boundaries):
        self.map = folium.Map(location=(51.250982119671754, 10.489567530592556), zoom_start=6)
        self.filtered_bookings = filtered_bookings
        self.airports = airports
        self.fir_information = fir_information
        self.fir_boundaries = fir_boundaries
        self.fir_idents = []
        self.style = {'fillColor': '#f5532f80', 'color': '#ff213680'}
        self.popup_text = None
        self.set_marker = False

        self.populate_map()

    def populate_map(self):
        online_stations = self.filtered_bookings["airport"].unique()
        airport_codes = self.airports["ICAO"]
        alt_airport_codes = self.airports["IATA/LID"]
        firs = self.airports["FIR"]
        fir_cs_prefix = self.fir_information["CALLSIGN PREFIX"]

        for icao in online_stations:
            self.set_marker = False

            pos = self.filtered_bookings.loc[self.filtered_bookings["airport"] == icao, "position"]
            pos_time = self.filtered_bookings.loc[self.filtered_bookings["airport"] == icao,
                       "position":"end"]  # .to_string(index=False)
            pos_time_html = pos_time.to_html(index=False)

            iframe = folium.IFrame(html=pos_time_html, width=300, height=200)
            self.popup_text = folium.Popup(iframe, max_width=2650, parse_html=True)

            matching_on_icao = airport_codes.str.match(icao).any()
            matching_on_alt_airport_code = alt_airport_codes.str.match(icao).any()
            matching_on_fir = firs.str.match(icao).any()
            matching_on_cs_prefix = fir_cs_prefix.str.match(icao).any()
            number_of_matches = airport_codes.str.match(icao).values[1]

            # Station ID matches on both the airport and a FIR (sometimes happens in Russia)
            if (matching_on_icao and matching_on_fir) or (matching_on_icao and matching_on_cs_prefix):
                self.handle_icao(icao, number_of_matches, pos)
                self.handle_fir(icao, pos)

            elif (matching_on_alt_airport_code and matching_on_fir) or (
                    matching_on_alt_airport_code and matching_on_cs_prefix):
                self.handle_alt_airport_code(icao, pos)
                self.handle_fir(icao, pos)

            # Station ID is an airport and has the normal ICAO identifier
            elif matching_on_icao:
                self.handle_icao(icao, number_of_matches, pos)

            # Station ID is an alternate callsign (thanks for nothing, UK)
            elif matching_on_alt_airport_code:
                self.handle_alt_airport_code(icao, pos)

            # Station ID is an FIR identifier
            else:
                self.handle_fir(icao, pos)

    def handle_icao(self, icao_code, n_matches, position):
        # Airport has no duplicates
        if n_matches == 1:
            lat = self.airports.loc[self.airports["ICAO"] == icao_code, "LAT"].item()
            long = self.airports.loc[self.airports["ICAO"] == icao_code, "LONG"].item()
        # Airport has duplicates, but coordinates are the same --> take the first entry
        else:
            lat = self.airports.loc[self.airports["ICAO"] == icao_code, "LAT"].values[0]
            long = self.airports.loc[self.airports["ICAO"] == icao_code, "LONG"].values[0]
        if position.str.contains("DEL|GND|TWR").any():
            folium.Marker(location=(lat, long), popup=self.popup_text, tooltip=icao_code).add_to(self.map)
            self.set_marker = True
        if position.str.contains("APP").any():
            if not self.set_marker:
                folium.Marker(location=(lat, long), popup=self.popup_text, tooltip=icao_code).add_to(self.map)
            folium.CircleMarker(location=(lat, long), radius=25, color="#3186cc", fill=True, fill_color="#3186cc",
                                tooltip=icao_code).add_to(self.map)

    def handle_alt_airport_code(self, icao_code, position):
        lat = self.airports.loc[self.airports["IATA/LID"] == icao_code, "LAT"].item()
        long = self.airports.loc[self.airports["IATA/LID"] == icao_code, "LONG"].item()
        if position.str.contains("DEL|GND|TWR").any():
            folium.Marker(location=(lat, long), popup=self.popup_text, tooltip=icao_code).add_to(self.map)
            self.set_marker = True
        if position.str.contains("APP").any():
            if not self.set_marker:
                folium.Marker(location=(lat, long), popup=self.popup_text, tooltip=icao_code).add_to(self.map)
            folium.CircleMarker(location=(lat, long), radius=25, color="#3186cc", fill=True, fill_color="#3186cc",
                                tooltip=icao_code).add_to(self.map)

    def handle_fir(self, icao_code, position):
        fir_id = (icao_code + "-" + position)
        for fir_id in fir_id:
            if "_" in fir_id:
                fir_id_formatted = fir_id.split("_")[0]
            else:
                fir_id_formatted = fir_id.split("-")[0]
            fir_csp = "_".join(fir_id_formatted.split("-")[:2])
            fir_icao = fir_csp.split("_")[0]

            # The FIR identifier matches in the GeoJSON db
            if self.fir_boundaries["id"].str.match(fir_id_formatted).any():
                print("{} produced a direct FIR match.".format(fir_id_formatted))
                bnd_polygon = self.fir_boundaries.loc[self.fir_boundaries["id"] == fir_id_formatted, "geometry"]
                folium.GeoJson(bnd_polygon, tooltip=fir_id_formatted, style_function=lambda x: self.style).add_to(
                    self.map)

            # No exact match in GeoJSON boundary database --> Map the callsign prefix to the corresponding FIR id
            elif self.fir_information["CALLSIGN PREFIX"].str.match(fir_csp).any():
                print("{} has no direct FIR match. Matching the callsign prefix {}.".format(fir_id_formatted, fir_csp))
                fir_id_alt = self.fir_information.loc[
                    self.fir_information["CALLSIGN PREFIX"] == fir_csp, "FIR BOUNDARY"].item()
                bnd_polygon = self.fir_boundaries.loc[self.fir_boundaries["id"] == fir_id_alt, "geometry"]
                folium.GeoJson(bnd_polygon, tooltip=fir_csp, style_function=lambda x: self.style).add_to(self.map)
            # The callsign prefix didn't match either --> Discard the suffix and match on the ICAO only (inaccurate, but hey, what can ya do?)
            elif self.fir_boundaries["id"].str.match(fir_icao).any():
                print("{} failed. Matching on {}.".format(fir_csp, fir_icao))
                bnd_polygon = self.fir_boundaries.loc[self.fir_boundaries["id"] == fir_icao, "geometry"]
                folium.GeoJson(bnd_polygon, tooltip=fir_icao, style_function=lambda x: self.style).add_to(self.map)

    def draw(self) -> folium.Map:
        return self.map


class Renderer(object):
    def __init__(self, bookings_url, vatspy_path, boundaries_path):
        self.booking_data = json.loads(urlopen(bookings_url).read().decode())
        self.bookings = Bookings(booking_data=self.booking_data).df
        self.airports = Airports(vatspy_path).df
        self.fir = FIRs(vatspy_path, boundaries_path)
        self.rendered_map = None
        self.desired_bookings = None

    def render(self, timestamp: pd.Timestamp):
        fir_info = self.fir.fir_info
        fir_bounds = self.fir.fir_boundaries

        desired_date = timestamp.date()
        desired_time = timestamp.time()

        self.desired_bookings = self.bookings[
            (self.bookings["date"] == desired_date) & (self.bookings["start"] <= desired_time) & (
                    desired_time < self.bookings["end"])]
        self.desired_bookings = self.desired_bookings.sort_values("airport")

        self.rendered_map = Map(self.desired_bookings, self.airports, fir_info, fir_bounds).draw()

    def get_map(self) -> folium.Map:
        self.rendered_map.save("{}/vatsimBookingMap.html".format(os.getcwd()))
        return self.rendered_map

    def get_desired_bookings(self):
        return self.desired_bookings
