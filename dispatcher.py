import asyncio
import re
import csv
import requests
from playwright.async_api import async_playwright

CURRENT_YEAR = 2026
CONCURRENCY_LIMIT = 5  # If the server still drops too many, lower this to 3.

# --- MODULE 1: THE GIS HARVESTER ---
def pull_gis_batch(limit=100):
    print(f"\n[GIS HARVESTER] Waking up. Querying Lee County API for {limit} properties...")
    url = "https://services2.arcgis.com/LvWGAAhHwbCJ2GMP/arcgis/rest/services/Lee_County_Parcels/FeatureServer/0/query"
    payload = {
        "where": "DORCODE = '01'", 
        "outFields": "STRAP, SITEADDR, SITECITY, MINBUILTY, O_NAME, O_STATE",
        "returnGeometry": "false",
        "resultRecordCount": limit,
        "f": "json"
    }
    
    try:
        response = requests.get(url, params=payload)
        data = response.json()
        features = data.get('features', [])
        print(f"[GIS HARVESTER] Successfully pulled {len(features)} properties.")
        return [f['attributes'] for f in features]
    except Exception as e:
        print(f"[GIS HARVESTER] Failed to pull data: {e}")
        return []

# --- MODULE 2 & 3: THE BREACHER & AUDITOR (CONCURRENT WORKER) ---
async def process_property(prop, context, writer, csv_lock, file):
    strap = prop.get("STRAP", "")
    address = prop.get("SITEADDR", "Unknown")
    year_built = prop.get("MINBUILTY") or CURRENT_YEAR 
    
    page = await context.new_page()
    target_url = "https://aca-prod.accela.com/LEECO/Cap/CapHome.aspx?module=Permitting&TabName=Permitting"
    
    print(f"[THREAD] Starting: {address} (STRAP: {strap})")
    
    try:
        # Increased global navigation timeout to 60 seconds for slow servers
        await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(1)

        start_date = page.locator('input[title*="Start Date"], input[name*="StartDate"]').first
        # THE FIX: Increased patience. Give the server 30 seconds to render the page under load.
        await start_date.wait_for(state="visible", timeout=30000)
        
        await start_date.evaluate("""(el) => {
            el.value = '01/01/1990';
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
        }""")

        parcel = page.locator('input[title*="Parcel"], input[name*="ParcelNo"]').first
        await parcel.evaluate(f"""(el) => {{
            el.value = '{strap}';
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}""")

        await parcel.focus()
        await page.keyboard.press("Enter")
        
        try:
            search_btn = page.locator('a.aca_btn:has-text("Search")').first
            await search_btn.click(timeout=2000)
        except:
            pass 

        try:
            # Increased patience for the database query response
            results_indicator = page.locator('tr.aca_header_row, span:has-text("Your search returned no results")').first
            await results_indicator.wait_for(state="visible", timeout=25000)
            await asyncio.sleep(0.5) 
        except:
            pass
        
        body_text_master = ""
        while True:
            body_text_master += await page.inner_text("body")
            next_button = page.locator('a:has-text("Next"), a[title*="Next"], .aca_pagination a:has-text("Next")').first
            
            if await next_button.count() > 0 and await next_button.is_visible():
                await next_button.click(force=True) 
                await asyncio.sleep(2) 
            else:
                break 

        roof_year = None
        if "Your search returned no results" not in body_text_master:
            rof_matches = re.findall(r'ROF(\d{4})', body_text_master)
            if rof_matches:
                roof_year = max([int(year) for year in rof_matches])
        
        if roof_year:
            roof_age = CURRENT_YEAR - roof_year
        else:
            roof_age = CURRENT_YEAR - year_built

        if roof_age >= 15:
            print(f"🚨 [SCRIBE] 15-Year Rule! Saving {address} to CSV.")
            async with csv_lock:
                writer.writerow([
                    strap, address, prop.get("SITECITY"), prop.get("O_NAME"), 
                    prop.get("O_STATE"), year_built, roof_year or "None", roof_age, "INSPECTION REQUIRED"
                ])
                file.flush() 
        else:
            print(f"✅ [AUDITOR] {address} roof is {roof_age} years old. Skipping.")

    except Exception as e:
        print(f"❌ [BREACHER] Error on STRAP {strap}: {e}")
    finally:
        await page.close()

# --- MODULE 4: THE MASTER ORCHESTRATOR ---
async def run_orchestration():
    properties = pull_gis_batch(limit=100) 
    if not properties:
        return

    csv_filename = "15yr_roof_inspections.csv"
    
    csv_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    with open(csv_filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(["STRAP", "Address", "City", "Owner Name", "Owner State", "Year Built", "Last Roof Permit", "Roof Age", "Status"])

        async with async_playwright() as p:
            print(f"\n[DISPATCHER] Launching Playwright Swarm ({CONCURRENCY_LIMIT} simultaneous tabs)...")
            browser = await p.chromium.launch(headless=True)
            
            async def bounded_process(prop):
                async with semaphore:
                    # THE FIX: Create a fully isolated "Incognito" context for every single property
                    context = await browser.new_context(viewport={'width': 1280, 'height': 1024})
                    try:
                        await process_property(prop, context, writer, csv_lock, file)
                    finally:
                        # Ensure we close the context to prevent RAM leaks
                        await context.close()

            tasks = [bounded_process(prop) for prop in properties]
            
            # Fire them all off concurrently
            await asyncio.gather(*tasks)
            
            print("\n[DISPATCHER] Batch complete. Closing browser swarm.")
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_orchestration())