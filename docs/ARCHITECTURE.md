# Architecture: The Spillover Engine

## Technology Stack
- **Python 3.10+**: Chosen for its rich ecosystem in data science and ease of deployment.
- **Pandas**: Crucial for handling "messy" government datasets.
  - **Normalization**: Handles multi-line headers and varied column naming (e.g., "Foreign State of Chargeability" vs "Place of Birth").
  - **Disclosure Handling**: Efficiently converts 'D' strings to integer 1 across large datasets.
- **Streamlit**: Provides a rapid, production-ready frontend for Python-based data models.
- **Plotly**: Used for interactive visualizations like the Waterfall Chart and Supply/Demand Area charts.

## Core Components

### 1. Data Parsers (`src/parsers`)
- **BaseParser**: Standardizes headers and cleans disclosure values.
- **DOSParser**: Specifically sums Family-Based (FB) usage (F1-F4, FX) to determine potential spillover.
- **InventoryParser**: Extracts specific category inventory (e.g., India EB-1) and applies the 2.2x dependent multiplier.

### 2. Logic Engine (`src/engine`)
- **RedistributionEngine**: Implements the "75-Country Freeze" logic, zeroing out volumes for restricted countries and calculating the resulting "savings".
- **DemandModeler**: Calculates burn rates and projects clearance dates based on remaining inventory.

## Data Flow
1. Government CSV/Excel $\rightarrow$ `BaseParser` (Normalization)
2. Normalized Data $\rightarrow$ `RedistributionEngine` (Freeze logic applied)
3. Resulting Savings + FB Floor $\rightarrow$ Final EB-1 Supply calculation.
4. EB-1 Supply vs Inventory $\rightarrow$ `DemandModeler` $\rightarrow$ Predictor Scores.
