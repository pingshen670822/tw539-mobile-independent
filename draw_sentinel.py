#!/usr/bin/env python3
"""開獎前常駐哨兵：等待當日官方新期別，並在公開頁落後時通知雲端主流程。"""
import json
import time
import urllib.request
from datetime import datetime

from cloud_pipeline import TAIPEI, fetch_latest

PUBLIC_HEALTH='https://pingshen670822.github.io/tw539-mobile-independent/system-health.json'


def public_health():
    stamp=str(int(time.time()))
    request=urllib.request.Request(
        f'{PUBLIC_HEALTH}?sentinel={stamp}',
        headers={'User-Agent':'TW539-draw-sentinel/1.0','Cache-Control':'no-cache'})
    with urllib.request.urlopen(request,timeout=8) as response:
        return json.loads(response.read().decode('utf-8'))


def main():
    now=datetime.now(TAIPEI)
    if now.weekday()==6:
        print('星期日無開獎，哨兵結束')
        return 0
    target=now.date().isoformat()
    try:
        official=fetch_latest()
        health=public_health()
    except Exception as exc:
        print(f'哨兵瞬時讀取失敗，繼續巡檢：{exc}')
        return 10
    official_date=str(official.get('draw_date') or '')
    public_date=str(health.get('latest_draw_date') or '')
    same_period=str(health.get('latest_period'))==str(official.get('period'))
    if official_date>=target and public_date>=official_date and same_period:
        print(json.dumps({'哨兵':'當日已同步','官方日期':official_date,'公開日期':public_date},ensure_ascii=False))
        return 0
    if official_date>=target and (public_date<official_date or not same_period):
        print(json.dumps({'哨兵':'偵測到新期別','官方日期':official_date,'公開日期':public_date},ensure_ascii=False))
        return 20
    if now.hour>=21 and public_date<target:
        print(json.dumps({'哨兵':'三十分鐘救援','目標日期':target,'公開日期':public_date},ensure_ascii=False))
        return 20
    print(json.dumps({'哨兵':'等待當日官方新期別','目標日期':target,'官方日期':official_date},ensure_ascii=False))
    return 10


if __name__=='__main__':
    raise SystemExit(main())
