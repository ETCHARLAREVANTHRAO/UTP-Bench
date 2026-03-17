import pandas as pd
from pandas import DataFrame
from typing import Optional
import os 
import sys
import numpy as np

# Add project root to path to allow importing utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from utils.func import extract_before_parenthesis


class Flights:

    def __init__(self, path: Optional[str] = None):
        """Flight API backed by the local Dataset_v1/flight.csv.

        We normalize column names so that legacy evaluation code that expects
        columns like 'Flight Number', 'OriginCityName', 'DestCityName',
        'Price', and 'FlightDate' keeps working.
        """
        if path is None:
            # Go up 3 levels from comman_metrices/tools/flights/
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            path = os.path.join(project_root, "Dataset_v1", "flight.csv")

        self.path = path
        self.data: Optional[DataFrame] = None

        try:
            self.load_db()
            print("Flights API loaded.")
        except Exception as e:
            print(f"Error loading Flights DB: {e}")

    def load_db(self):
        """Load the flight database and harmonize column names."""
        df = pd.read_csv(self.path)

        # Map to legacy column names expected by commonsense/hard constraints.
        if "Flight Number" not in df.columns and "flight_no" in df.columns:
            df["Flight Number"] = df["flight_no"]

        if "OriginCityName" not in df.columns:
            if "matched_dep_city" in df.columns:
                df["OriginCityName"] = df["matched_dep_city"].apply(extract_before_parenthesis)
            elif "dep_city" in df.columns:
                df["OriginCityName"] = df["dep_city"].apply(extract_before_parenthesis)
        else:
            df["OriginCityName"] = df["OriginCityName"].apply(extract_before_parenthesis)

        if "DestCityName" not in df.columns:
            if "matched_arr_city" in df.columns:
                df["DestCityName"] = df["matched_arr_city"].apply(extract_before_parenthesis)
            elif "arr_city" in df.columns:
                df["DestCityName"] = df["arr_city"].apply(extract_before_parenthesis)
        else:
            df["DestCityName"] = df["DestCityName"].apply(extract_before_parenthesis)

        if "Price" not in df.columns and "price" in df.columns:
            # Strip currency symbols and commas, convert to float.
            price_series = df["price"].astype(str).str.replace(r"[^0-9.]", "", regex=True)
            df["Price"] = pd.to_numeric(price_series, errors="coerce")

        if "FlightDate" not in df.columns and "dep_date" in df.columns:
            df["FlightDate"] = df["dep_date"]

        self.data = df

    def run(self,
            origin: str,
            destination: str,
            departure_date: str,
            ) -> DataFrame:
        """Search for flights by origin, destination, and departure date."""
        if self.data is None: return "Database not loaded."
        
        # Ensure column names match what your DB has. 
        # Standard TripCraft names: OriginCityName, DestCityName, FlightDate
        # You might need to map them if your DB is different.
        
        results = self.data[self.data["OriginCityName"] == origin]
        results = results[results["DestCityName"] == destination]
        results = results[results["FlightDate"] == departure_date]

        if len(results) == 0:
            return "There is no flight from {} to {} on {}.".format(origin, destination, departure_date)
        return results
    
    def run_for_annotation(self,
            origin: str,
            destination: str,
            departure_date: str,
            ) -> DataFrame:
        """Search for flights by origin, destination, and departure date."""
        if self.data is None: return "Database not loaded."

        results = self.data[self.data["OriginCityName"] == extract_before_parenthesis(origin)]
        results = results[results["DestCityName"] == extract_before_parenthesis(destination)]
        results = results[results["FlightDate"] == departure_date]

        return results.to_string(index=False)

    def get_city_set(self):
        city_set = set()
        # This function seems unused or needs specific column indices
        return city_set
