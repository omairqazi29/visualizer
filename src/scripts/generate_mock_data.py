import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def generate_dos_data():
    countries = ["India", "China", "Mexico", "Philippines", "Dominican Republic", "Vietnam", "UK", "Canada"]
    categories = ["F1", "F2A", "F2B", "F3", "F4", "FX", "E11", "E12", "E13"]
    
    data = []
    for country in countries:
        for cat in categories:
            # Random count or 'D'
            if np.random.rand() < 0.1:
                count = 'D'
            else:
                count = np.random.randint(10, 5000)
            data.append({
                "Foreign State of Chargeability": country,
                "Class of Admission": cat,
                "Issuances": count
            })
    
    df = pd.DataFrame(data)
    df.to_csv("data/dos_issuances_2025.csv", index=False)
    print("Generated data/dos_issuances_2025.csv")

def generate_inventory_data():
    countries = ["India", "China", "Rest of World"]
    categories = ["EB1", "EB2", "EB3"]
    
    # Mountain vs Valley logic for India EB1
    # India EB1: 21,295 before April 2023, 597 until end of 2023
    data = []
    
    # India EB1 Mountain
    data.append({
        "Place of Birth": "India",
        "Visa Category": "EB1",
        "Priority Date": "2022-01-01",
        "Count": 21295
    })
    
    # India EB1 Valley
    data.append({
        "Place of Birth": "India",
        "Visa Category": "EB1",
        "Priority Date": "2023-06-01",
        "Count": 597
    })
    
    # Other random data
    data.append({
        "Place of Birth": "China",
        "Visa Category": "EB1",
        "Priority Date": "2022-01-01",
        "Count": 5000
    })
    
    df = pd.DataFrame(data)
    df.to_csv("data/eb_inventory_jan_2026.csv", index=False)
    print("Generated data/eb_inventory_jan_2026.csv")

if __name__ == "__main__":
    generate_dos_data()
    generate_inventory_data()
