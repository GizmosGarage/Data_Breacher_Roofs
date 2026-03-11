# Data_Breacher_Roofs

An automated data extraction pipeline designed to identify property characteristics and permit histories in Lee County, Florida. 

This tool operates in two phases:
1. **GIS Harvester:** Queries the Lee County ArcGIS REST API to pull target property data (DORCODE '01').
2. **Playwright Swarm:** Dispatches a bounded, asynchronous swarm of headless browsers to query the Accela permit database, injecting precise JavaScript to bypass date-masking fields and extract the most recent roof permit year.

## Prerequisites
* Python 3.8+
* Playwright

## Installation

1. Clone the repository and navigate to the directory:
   ```bash
   git clone <your-repository-url>
   cd <your-repository-directory>
