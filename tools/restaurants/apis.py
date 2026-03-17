import pandas as pd
from pandas import DataFrame
from typing import Optional
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from utils.func import extract_before_parenthesis


class Restaurants:
    def __init__(self, path: Optional[str] = None):
        # Default to local Dataset_v1/res.csv
        if path is None:
            # Go up 3 levels from comman_metrices/tools/restaurants/
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            path = os.path.join(base_dir, "Dataset_v1", "res.csv")
        self.path = path
        try:
            self.load_db()
            print("Restaurants loaded.")
        except Exception as e:
            print(f"Error loading Restaurants DB: {e}")
            self.data = None

    def load_db(self):
        df = pd.read_csv(self.path)

        # Normalise column names expected by constraints code
        # City column (expected: 'City')
        if "City" not in df.columns and "city" in df.columns:
            df["City"] = df["city"].apply(extract_before_parenthesis)
        elif "City" in df.columns:
            df["City"] = df["City"].apply(extract_before_parenthesis)

        # Average cost (expected: 'avg_cost')
        if "avg_cost" not in df.columns:
            if "Estimated Price(INR)" in df.columns:
                # Use estimated price as proxy for avg_cost
                df["avg_cost"] = df["Estimated Price(INR)"]

        # Cuisines column (expected: 'cuisines')
        if "cuisines" not in df.columns and "CUISINE_GROUPS" in df.columns:
            df["cuisines"] = df["CUISINE_GROUPS"]

        # Rating column (expected: 'rating')
        if "rating" not in df.columns and "rating" in df.columns:
            df["rating"] = df["rating"]

        self.data = df

    def run(self,
            city: str,
            ) -> DataFrame:
        """Search for restaurant."""
        if self.data is None:
            return "Database not loaded."
        # Use normalised 'City' column for compatibility with constraints
        col = "City" if "City" in self.data.columns else "city"
        results = self.data[self.data[col] == city]
        if len(results) == 0:
            return "There is no restaurant in this city."
        return results

    def run_for_annotation(self,
            city: str,
            ) -> DataFrame:
        """Search for restaurant for annotation."""
        if self.data is None:
            return "Database not loaded."
        city_clean = extract_before_parenthesis(city)
        col = "City" if "City" in self.data.columns else "city"
        results = self.data[self.data[col] == city_clean]
        return results
