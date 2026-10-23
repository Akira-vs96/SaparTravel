"""Management layout and native-dialog keyboard checks on a disposable demo."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
from playwright.async_api import async_playwright


async def run(base_url):
    source = Path('frontend/src/i18n.js').resolve()
    program = "import {translate} from " + json.dumps(source.as_uri()) + ";console.log(JSON.stringify(Object.fromEntries(['ru','kk','en'].map(l=>[l,Object.fromEntries(['newTour','users','analytics'].map(k=>[k,translate(l,k)]))]))));"
    labels = json.loads(subprocess.check_output(['node','--input-type=module','-e',program],text=True))
    artifacts=Path('test-results');artifacts.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        context=await browser.new_context()
        auth=await context.request.post(base_url+'/api/v1/auth/login',data={
            'email':os.environ['E2E_ADMIN_EMAIL'],'password':os.environ['E2E_ADMIN_PASSWORD']})
        assert auth.status==200, 'Private administrator login failed'
        token=(await auth.json())['access_token']
        await context.add_init_script("localStorage.setItem('sapar-token',"+json.dumps(token)+");")
        page=await context.new_page();errors=[]
        page.on('pageerror',lambda error:errors.append(type(error).__name__))
        for lang in ('ru','kk','en'):
            for width in (360,768,1440):
                await page.set_viewport_size({'width':width,'height':1000})
                await page.goto(base_url+'/manage',wait_until='networkidle')
                await page.locator('.language-select').select_option(lang)
                await page.locator('.manage-tour-card').first.wait_for()
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Workspace overflow'
                create=page.get_by_role('button',name=labels[lang]['newTour'],exact=True)
                await create.click()
                dialog=page.get_by_role('dialog');await dialog.wait_for()
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Dialog overflow'
                await dialog.locator('button').first.focus()
                await page.keyboard.press('Shift+Tab')
                assert await dialog.evaluate('(d)=>d.contains(document.activeElement)'), 'Dialog lost keyboard focus'
                await page.keyboard.press('Tab')
                assert await dialog.evaluate('(d)=>d.contains(document.activeElement)'), 'Dialog focus wrap failed'
                await page.keyboard.press('Escape')
                await dialog.wait_for(state='hidden')
                await page.locator('.manage-toolbar .tabs').get_by_role('button',name=labels[lang]['users'],exact=True).click()
                await page.locator('table').first.wait_for()
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Users table overflow'
                await page.locator('.manage-toolbar .tabs').get_by_role('button',name=labels[lang]['analytics'],exact=True).click()
                await page.locator('.metric-grid').wait_for()
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Analytics overflow'
                await page.screenshot(path=str(artifacts/f'management-analytics-{lang}-{width}.png'),full_page=True)
        assert not errors, 'JavaScript errors in management'
        print('PASS: management/users/analytics and keyboard dialogs in ru/kk/en at 360/768/1440')
        await browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:5173')
    asyncio.run(run(parser.parse_args().base_url.rstrip('/')))
