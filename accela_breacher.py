import asyncio
import re
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        context = await browser.new_context(viewport={'width': 1280, 'height': 1024})
        page = await context.new_page()

        target_url = "https://aca-prod.accela.com/LEECO/Cap/CapHome.aspx?module=Permitting&TabName=Permitting"

        try:
            print(f"Navigating to {target_url}...")
            await page.goto(target_url, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            print("Locating Start Date field...")
            start_date = page.locator('input[title*="Start Date"], input[name*="StartDate"]').first
            await start_date.wait_for(state="visible", timeout=10000)
            
            # The JS Injection that successfully beat the mask
            await start_date.evaluate("""(el) => {
                el.value = '01/01/1990';
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('blur', { bubbles: true }));
            }""")
            print("Start Date forcefully injected via JS.")

            print("Locating Parcel Number field...")
            parcel = page.locator('input[title*="Parcel"], input[name*="ParcelNo"]').first
            await parcel.evaluate("""(el) => {
                el.value = '35452402000370000';
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""")
            print("Parcel Number forcefully injected via JS.")

            print("Executing Search bypass...")
            # THE FIX: The "Enter Key" bypass.
            await parcel.focus()
            await page.keyboard.press("Enter")
            
            # Fallback: Target the EXACT visible Accela button class just in case
            try:
                search_btn = page.locator('a.aca_btn:has-text("Search")').first
                await search_btn.click(timeout=2000)
            except:
                pass # The Enter key likely triggered it, so we ignore this error.

            print("Awaiting results table (Giving the DB 10 seconds to pull data)...")
            await asyncio.sleep(10) 
            
            body_text = await page.inner_text("body")
            
            if "Your search returned no results" in body_text:
                print("No Roof Permits Found (This is an Open Lead!)")
                return
                
            # Extract the 4-digit year from the Record Number
            rof_matches = re.findall(r'ROF(\d{4})', body_text)
            
            if rof_matches:
                years = [int(year) for year in rof_matches]
                recent_year = max(years)
                print(f"✅ Discovered Most Recent Roof Year: {recent_year}")
            else:
                print("No Roof Permits Found (This is an Open Lead!)")

        except Exception as e:
            print(f"❌ An error occurred: {e}")
            await page.screenshot(path="error_screenshot.png")
            print("Saved an image of the failure to 'error_screenshot.png'.")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run())