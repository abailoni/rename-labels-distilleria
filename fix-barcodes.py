#!/usr/bin/env python3
"""
merge_barcodes.py

Usage:
  python merge_barcodes.py input.csv output.csv

What it does:
- Drops empty rows.
- Concatenates columns 2 .. (N-2) into a single 'barcode' string per row.
- Keeps column 1 (name/description) and the new 'barcode' column.
"""

import sys
import pandas as pd
import re

def main(inp, outp):
    # Read everything as string so 0's aren’t lost and NaNs are easy to handle
    df = pd.read_csv(inp, dtype=str, delimiter=";", header=None)

    # Normalize whitespace
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

    # Drop rows that are completely empty
    df = df.dropna(how="all")

    # Also drop rows where the first column is empty/NaN (often the blank separators)
    first_col = df.columns[0]
    df = df[~(df[first_col].isna() | (df[first_col].astype(str).str.strip() == ""))].copy()

    # Determine the columns that hold the split barcode digits:
    # from the second column to the third-to-last (i.e., ignore the last two columns)
    if df.shape[1] < 4:
        raise ValueError("Expected at least 4 columns (name + digits + 2 trailing columns).")

    digit_cols = df.columns[1:-2]  # second column up to (N-2)

    # Function to join only digits from the row cells, preserving order
    def join_digits(row):
        parts = []
        for c in digit_cols:
            val = row.get(c)
            if pd.isna(val):
                continue
            # keep only 0-9 (if there could be other characters)
            digits = re.sub(r"[^0-9]", "", str(val))
            if digits != "":
                parts.append(digits)
        return "".join(parts)

    df["barcode"] = df.apply(join_digits, axis=1)

    # Keep only first column and the new barcode
    out_df = df[[first_col, "barcode"]].reset_index(drop=True)

    # Optionally drop rows with empty barcode (if any)
    out_df = out_df[out_df["barcode"] != ""].copy()

    out_df.to_csv(outp, index=False)
    print(f"Saved {len(out_df)} rows to {outp}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python merge_barcodes.py input.csv output.csv")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
