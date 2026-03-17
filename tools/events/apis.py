import pandas as pd
from pandas import DataFrame
from typing import Optional
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from utils.func import extract_before_parenthesis


class Events:
    def __init__(self, path: Optional[str] = None):
        """Events DB backed by local Dataset_v1/final_events.csv by default."""
        if path is None:
            # Go up 3 levels from comman_metrices/tools/events/
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            path = os.path.join(base_dir, "Dataset_v1", "final_events.csv")

        self.path = path
        try:
            self.load_db()
            print("Events loaded.")
        except Exception as e:
            print(f"Error loading Events DB: {e}")
            self.data = None

    def load_db(self):
        df = pd.read_csv(self.path)

        # Normalise columns expected by constraint code
        # Event name (expected: 'name')
        if "name" not in df.columns and "Event Name" in df.columns:
            df["name"] = df["Event Name"]

        # City (expected: 'city' and often 'City')
        if "city" in df.columns:
            df["city"] = df["city"].apply(extract_before_parenthesis)
        elif "matched_city" in df.columns:
            df["city"] = df["matched_city"].apply(extract_before_parenthesis)
        
        if "City" not in df.columns and "city" in df.columns:
            df["City"] = df["city"]
        elif "City" in df.columns:
            df["City"] = df["City"].apply(extract_before_parenthesis)

        self.data = df

    def run(self,
            city: str,
            date: str,
            ) -> DataFrame:
        """Search for events by city (date currently ignored)."""
        if self.data is None:
            return "Database not loaded."

        city_col = "city" if "city" in self.data.columns else ("City" if "City" in self.data.columns else None)
        if city_col is None:
            return "City column not found in Events DB."

        results = self.data[self.data[city_col] == city]
        return results
