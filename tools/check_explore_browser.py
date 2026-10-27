"""Local authenticated UI fixtures only, never a production session or API key.

Requires Playwright and installed Chrome. Map tiles are mocked, not downloaded.
"""
from __future__ import annotations

import argparse
import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EVENTS = [
    {'event_id':'unified','place':'Los Santos, Santander','magnitude':4.1,'magnitude_type':'Mw',
     'depth_km':142,'latitude':6.76,'longitude':-73.16,'origin_time':'2026-10-26T14:30:00Z','agency':'SGC',
     'review_status':'Revisado','source_reports':[
       {'agency':'SGC','magnitude':4.1,'magnitude_type':'Mw','official_url':'https://www.sgc.gov.co/sismos'},
       {'agency':'USGS','magnitude':4.0,'magnitude_type':'mb','official_url':'https://earthquake.usgs.gov/'}]},
    {'event_id':'second','place':'Cerca de El Calvario, Meta','magnitude':3.2,'depth_km':25,
     'latitude':4.37,'longitude':-73.71,'origin_time':'2026-10-26T12:42:00Z','agency':'USGS'},
    {'event_id':'candidate','place':'Señal multiestación sin epicentro confirmado','magnitude':None,
     'preliminary':True,'latitude':None,'longitude':None,'detected_at':'2026-10-26T13:15:00Z','agency':'Seismik / SeedLink',
     'own_magnitude':{'value':None,'validation_status':'beta_unvalidated'}},
    {'event_id':'xss','place':'<img src=x onerror=alert(1)>','magnitude':None,'latitude':None,
     'origin_time':'2026-10-26T12:00:00Z','agency':'Test'}]
ACCOUNT = {'plan':{'name':'Always Free with API Key','requests_per_month':30000,
           'requests_per_minute':60,'requests_per_day':10000},
           'quota_usage':{p:{'used':n,'resets_at':'2026-11-01T00:00:00Z'} for p,n in [('month',214),('day',32),('minute',1)]}}


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        super().end_headers()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT/'web')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    state={'signed_in':True,'quota':False,'empty':False,'partial':False,'calls':0}
    api_calls=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1150},color_scheme='light')
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('console',lambda msg: errors.append(msg.text) if msg.type=='error' and 'Content Security Policy' in msg.text else None)

        def api(route):
            path=route.request.url.split('/v1/',1)[1].split('?')[0]
            api_calls.append({'path':path,'headers':route.request.headers})
            if path=='oauth/logout':
                state['signed_in']=False
                route.fulfill(status=204)
            elif not state['signed_in']:
                route.fulfill(status=401,json={'detail':'Session expired'})
            elif path=='oauth/session':
                route.fulfill(json={'uid':'local-fixture','name':'Cuenta de prueba','email':'test@example.com'})
            elif path=='developer/account':
                route.fulfill(json=ACCOUNT)
            elif path=='developer/explore/history':
                state['calls']+=1
                if state['quota']:
                    route.fulfill(status=429,headers={'Retry-After':'60'},json={'detail':'Quota exceeded'})
                else:
                    route.fulfill(json={'events':[] if state['empty'] else EVENTS,'generated_at':'2026-10-26T16:00:00Z',
                                  'errors':[{'source_id':'sgc_colombia'}] if state['partial'] else []})
            else:
                raise AssertionError(path)

        page.route('**/v1/**',api)
        page.route('https://tile.openstreetmap.org/**',lambda r:r.fulfill(content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#d9e4e3"/><path d="M0 160L100 40 256 110M70 256L200 0" fill="none" stroke="#b5cfb4" stroke-width="40"/></svg>'))
        url=f'http://127.0.0.1:{server.server_port}/explore.html'
        page.goto(url)
        page.wait_for_selector('.event-card')
        assert page.locator('.event-card').count()==4
        assert page.locator('#map-count').inner_text()=='2 epicentros · 2 sin ubicación confirmada'
        assert page.locator('#event-list img').count()==0
        page.locator('.event-card').first.click()
        assert 'USGS · 4,0 mb' in page.locator('#event-detail').inner_text()
        loaded_calls=state['calls']
        page.locator('#local-search').fill('Los Santos')
        assert page.locator('.event-card').count()==1
        page.locator('#fit-map').click()
        assert state['calls']==loaded_calls
        page.locator('#local-search').fill('')
        page.screenshot(path=str(args.output/'explore-desktop-light.png'),full_page=True)
        page.emulate_media(color_scheme='dark')
        page.screenshot(path=str(args.output/'explore-desktop-dark.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(args.output/'explore-mobile-dark.png'),full_page=True)
        page.locator('.event-card').nth(2).click()
        assert 'Sin epicentro confirmado' in page.locator('#event-detail').inner_text()
        assert 'Magnitud propia no disponible' in page.locator('#event-detail').inner_text()
        page.set_viewport_size({'width':1440,'height':1150})
        state['partial']=True
        page.locator('#search').click()
        page.wait_for_function("document.querySelector('#message').textContent.includes('sgc_colombia')")
        state['empty']=True
        page.locator('#search').click()
        page.wait_for_selector('.empty-state')
        assert page.locator('.event-card').count()==0
        state['quota']=True
        page.locator('#search').click()
        page.wait_for_function("document.querySelector('#message').textContent.includes('Alcanzaste')")
        attempts=state['calls']
        page.locator('#search').click()
        assert state['calls']==attempts
        page.locator('#logout').click()
        page.wait_for_selector('#login-gate',state='visible')
        assert page.locator('#search').is_disabled()
        assert page.locator('.event-card').count()==0
        assert all('x-seismik-api-key' not in r['headers'] for r in api_calls)
        assert not errors, errors
        browser.close()
    server.shutdown()
    print(json.dumps({'passed':True,'history_queries':state['calls'],'checks':['light/dark/mobile','session_only','no_key_headers','shared_meter_display','local_filters_no_queries','null_coordinates','agency_magnitudes','xss_text','partial_sources','empty','quota_retry','logout','strict_csp']}))


if __name__=='__main__':
    main()
