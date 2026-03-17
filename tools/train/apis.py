import os
import sys
from typing import Optional

import pandas as pd
from pandas import DataFrame

# Allow importing project-level utilities
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from utils.func import extract_before_parenthesis


class Trains:
    """Simple wrapper around the local train database.

    Backed by Dataset_v1/train.csv by default. Exposes basic search helpers
    by origin and destination city names.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        if path is None:
            # Go up 3 levels from comman_metrices/tools/train/
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            path = os.path.join(base_dir, "Dataset_v1", "train.csv")

        self.path = path
        self.data: Optional[DataFrame] = None

        try:
            self.load_db()
            print("Trains loaded.")
        except Exception as e:
            print(f"Error loading Trains DB: {e}")
            self.data = None

    def load_db(self) -> None:
        """Load the trains CSV into a DataFrame."""
        df = pd.read_csv(self.path)
        self.data = df

    def run(self, origin: str, destination: str) -> DataFrame:
        """Return all train segments between origin and destination cities.

        Uses 'matched_origin' and 'matched_destination' columns from train.csv.
        City strings are cleaned with extract_before_parenthesis for safety.
        """
        if self.data is None:
            return "Database not loaded."

        origin_clean = extract_before_parenthesis(origin)
        dest_clean = extract_before_parenthesis(destination)

        if "matched_origin" not in self.data.columns or "matched_destination" not in self.data.columns:
            return "Required columns not found in train DB."

        results = self.data[
            (self.data["matched_origin"] == origin_clean)
            & (self.data["matched_destination"] == dest_clean)
        ]

        if len(results) == 0:
            return f"There is no train from {origin_clean} to {dest_clean}."

        return results

    def run_for_annotation(self, origin: str, destination: str) -> DataFrame:
        """Same as run(), but with cleaned origin/destination names.

        This keeps the interface similar to Flights.run_for_annotation.
        """
        if self.data is None:
            return "Database not loaded."

        origin_clean = extract_before_parenthesis(origin)
        dest_clean = extract_before_parenthesis(destination)

        if "matched_origin" not in self.data.columns or "matched_destination" not in self.data.columns:
            return "Required columns not found in train DB."

        results = self.data[
            (self.data["matched_origin"] == origin_clean)
            & (self.data["matched_destination"] == dest_clean)
        ]

        return results