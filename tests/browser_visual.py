"""Public screen matrix on a disposable running demo: 5 pages × 3 widths × 3 languages."""
import argparse,asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
async def main(base_url):
 Path("test-results").mkdir(exist_ok=True)
 async with async_playwright() as p:
  b=await p.chromium.launch(headless=True);context=await b.new_context();page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  for lang in ['ru','kk','en']:
   for width in [360,768,1440]:
    await page.set_viewport_size({'width':width,'height':1000})
    await page.goto(base_url+'/');await page.locator('.language-select').select_option(lang)
    for route in ['/','/explore','/trips/almaty-lakes-and-canyons','/recommendations?budget=500000&category=Nature&duration_max=7&travelers=2','/login']:
     await page.goto(base_url+route,wait_until='networkidle')
     if route.startswith('/recommendations'): await page.locator('.tour-card').first.wait_for(timeout=10000)
     measured=await page.evaluate('document.documentElement.scrollWidth');assert measured==width,(lang,width,route,measured)
     if route=='/':
      assert await page.locator('.journey-hero img').evaluate('(img)=>img.complete&&img.naturalWidth>0')
      if lang=='ru' and width==1440: await page.screenshot(path='test-results/visual-home-desktop.png',full_page=True)
     if lang=='kk' and width==360 and route.startswith('/recommendations'):await page.screenshot(path='test-results/visual-recommendations-mobile.png',full_page=True)
     if lang=='en' and width==360 and route.startswith('/trips'):await page.screenshot(path='test-results/visual-trip-mobile.png',full_page=True)
    print(json.dumps({'lang':lang,'width':width,'pages':5,'overflow':False}))
  assert not errors,errors
  print('PASS 45 screen/locale/width combinations; local hero loaded; no JS errors')
  await b.close()
if __name__ == "__main__":
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument("--base-url",default="http://127.0.0.1:5173")
 asyncio.run(main(parser.parse_args().base_url.rstrip("/")))
