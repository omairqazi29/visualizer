import pandas as pd
import numpy as np
import os


def generate_dos_data(directory="data/DOS"):
    if not os.path.exists(directory):
        os.makedirs(directory)

    months = [
        "OCTOBER 2024",
        "NOVEMBER 2024",
        "DECEMBER 2024",
        "JANUARY 2025",
        "FEBRUARY 2025",
        "MARCH 2025",
        "APRIL 2025",
        "MAY 2025",
        "JUNE 2025",
        "JULY 2025",
        "AUGUST 2025",
        "SEPTEMBER 2025",
    ]

    countries = [
        "India",
        "China - mainland born",
        "Mexico",
        "Philippines",
        "Dominican Republic",
        "Vietnam",
        "UK",
        "Canada",
    ]
    categories = ["F1", "F2A", "F2B", "F3", "F4", "FX", "E11", "E12", "E13"]

    for month in months:
        data = []
        for country in countries:
            for cat in categories:
                # Random count or 'D'
                if np.random.rand() < 0.1:
                    count = "D"
                elif np.random.rand() < 0.05:
                    count = "<10"
                else:
                    count = np.random.randint(10, 500)

                data.append(
                    {
                        "Foreign State of Chargeability": country,
                        "Visa Class": cat,
                        "Grand Total": count,
                    }
                )

        df = pd.DataFrame(data)
        file_path = os.path.join(
            directory,
            f"{month} - IV Issuances by FSC or Place of Birth and Visa Class.xlsx",
        )
        df.to_excel(file_path, index=False)
        print(f"Generated {file_path}")


def generate_inventory_data(file_path="data/eb_inventory_january_2026.xlsx"):
    # Mocking the USCIS Inventory format.
    # NOTE: These exact default filenames are used by pinned exact-assert tests in test_engine.py.
    # At runtime, data_discovery + Parser.latest() will prefer any newer-dated file present in data/.
    # Do not change the defaults (would require regenerating test data + updating asserts).
    writer = pd.ExcelWriter(file_path, engine="openpyxl")

    # India Sheet
    india_data = {
        "Preference Category": ["1st", "1st", "1st", "2nd", "3rd"],
        "Priority Date Month": ["January", "June", "December", "January", "January"],
        "Priority Date Year - 2022": [1000, 500, 200, 5000, 4000],
        "Priority Date Year - 2023": [100, 200, 300, 1000, 1000],
        "Priority Date Year - 2024": [50, 50, 50, 500, 500],
        "Priority Date Year - Prior Years": [15000, 0, 0, 20000, 15000],
    }
    df_india = pd.DataFrame(india_data)
    # Start at row 3 (0-indexed) to match InventoryParser (header=3)
    df_india.to_excel(
        writer, sheet_name="India (EB1 EW3 EB4 CRW EB5)", startrow=3, index=False
    )

    writer.close()
    print(f"Generated {file_path}")


def generate_pipeline_data(
    file_path="data/eb_i140_i360_i526_performance_data_fy2025_q4_v1.xlsx",
):
    # Mocking the I-140 Performance format.
    # NOTE: These exact default filenames are used by pinned exact-assert tests in test_engine.py.
    # At runtime, data_discovery + Parser.latest() will prefer any newer-dated file present in data/.
    # Do not change the defaults (would require regenerating test data + updating asserts).
    data = {
        "Country": ["INDIA", "CHINA", "MEXICO", "TOTAL"],
        "1st Preference (EB1)": [5000, 2000, 100, 10000],
        "2nd Preference (EB2)": [15000, 5000, 500, 30000],
        "3rd Preference (EB3)": [10000, 3000, 400, 20000],
        "TOTAL": [30000, 10000, 1000, 60000],
    }
    df = pd.DataFrame(data)
    df.to_excel(file_path, index=False)
    print(f"Generated {file_path}")


if __name__ == "__main__":
    generate_dos_data()
    generate_inventory_data()
    generate_pipeline_data()
