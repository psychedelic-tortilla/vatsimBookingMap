import datetime
import json
from urllib.request import urlopen

import folium
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
        self.set_marker = False

        self.populate_map()

    def populate_map(self):
        online_airports = self.filtered_bookings["airport"].unique()
        airport_code = self.airports["ICAO"]
        alt_airport_callsign = self.airports["IATA/LID"]

        for icao in online_airports:
            self.set_marker = False
            pos = self.filtered_bookings.loc[self.filtered_bookings["airport"] == icao, "position"]
            pos_time = self.filtered_bookings.loc[self.filtered_bookings["airport"] == icao,
                       "position":"end"]  # .to_string(index=False)
            pos_time_html = pos_time.to_html(index=False)
            # popup_text = ' '.join(map(str, pos.values))
            # popup_text = pos_time
            iframe = folium.IFrame(html=pos_time_html, width=300, height=300)
            popup_text = folium.Popup(iframe, max_width=2650, parse_html=True)

            matches = airport_code.str.match(icao)
            # Station ID is an airport and has the normal ICAO identifier
            if matches.any():
                # Airport has no duplicates
                if matches.value_counts().values[1] == 1:
                    lat = self.airports.loc[self.airports["ICAO"] == icao, "LAT"].item()
                    long = self.airports.loc[self.airports["ICAO"] == icao, "LONG"].item()
                # Airport has duplicates, but coordinates are the same --> take the first entry
                else:
                    lat = self.airports.loc[self.airports["ICAO"] == icao, "LAT"].values[0]
                    long = self.airports.loc[self.airports["ICAO"] == icao, "LONG"].values[0]
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
                    fir_csp = "_".join(fir_id_formatted.split("-")[:2])
                    fir_icao = fir_csp.split("_")[0]

                    # The FIR identifier matches in the GeoJSON db
                    if self.fir_boundaries["id"].str.match(fir_id_formatted).any():
                        print("{} produced a direct match.".format(fir_id_formatted))
                        bnd_polygon = self.fir_boundaries.loc[self.fir_boundaries["id"] == fir_id_formatted, "geometry"]
                        folium.GeoJson(bnd_polygon, tooltip=fir_id_formatted,
                                       style_function=lambda x: self.style).add_to(self.map)

                    # No exact match in GeoJSON boundary database --> Map the callsign prefix to the corresponding FIR id
                    elif self.fir_information["CALLSIGN PREFIX"].str.match(fir_csp).any():
                        print("{} has no direct match. Matching the callsign {}.".format(fir_id_formatted, fir_csp))
                        fir_id_alt = self.fir_information.loc[
                            self.fir_information["CALLSIGN PREFIX"] == fir_csp, "FIR BOUNDARY"].item()
                        bnd_polygon = self.fir_boundaries.loc[self.fir_boundaries["id"] == fir_id_alt, "geometry"]
                        folium.GeoJson(bnd_polygon, tooltip=fir_csp, style_function=lambda x: self.style).add_to(
                            self.map)
                    # The callsign prefix didn't match either --> Discard the suffix and match on the ICAO only (inaccurate, but hey, what can ya do?)
                    elif self.fir_boundaries["id"].str.match(fir_icao).any():
                        print("{} failed. Matching on {}.".format(fir_csp, fir_icao))
                        bnd_polygon = self.fir_boundaries.loc[self.fir_boundaries["id"] == fir_icao, "geometry"]
                        folium.GeoJson(bnd_polygon, tooltip=fir_icao, style_function=lambda x: self.style).add_to(
                            self.map)

    def draw(self) -> folium.Map:
        # self.map.save("vatsimBookingMap.html")
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
        self.rendered_map.save("L:\\Projects\\vatsimBookingMap\\vatsimBookingMap.html")
        return self.rendered_map

    def get_desired_bookings(self):
        return self.desired_bookings