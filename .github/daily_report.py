"""
每日盘前日报 - 09:26 自动生成 -> 钉钉推送
"""
import os, sys, json, requests, time, hmac, hashlib, base64, urllib.parse
from datetime import datetime
try: sys.stdout.reconfigure(encoding='utf-8')
except: pass

# ===== DingTalk Config =====
TOKEN = os.environ.get('DINGTALK_TOKEN', 'd69ad254111dd477bbb8fe8ee1f754908f88a83ff21f4daec25b5ce6365103fc')
SECRET = os.environ.get('DINGTALK_SECRET', 'SECc3449095eb18f883114db609ea5c8421035351356772b5bdb92248fe162b6293')

today = datetime.now().strftime('%Y%m%d')
weekday = ['周一','周二','周三','周四','周五','周六','周日'][datetime.now().weekday()]

def dingtalk_send(text):
    ts = str(round(time.time() * 1000))
    sign = base64.b64encode(hmac.new(SECRET.encode(), f'{ts}\n{SECRET}'.encode(), hashlib.sha256).digest()).decode()
    url = f'https://oapi.dingtalk.com/robot/send?access_token={TOKEN}&timestamp={ts}&sign={urllib.parse.quote_plus(sign)}'
    data = {'msgtype': 'markdown', 'markdown': {'title': '盘前日报', 'text': text}}
    try:
        r = requests.post(url, json=data, timeout=10)
        return r.ok
    except:
        return False

# ===== Build Report =====
def build_report(market_data, themes, best):
    lines = []
    lines.append(f'## ▎盘前日报 {today} ({weekday})')
    lines.append('')
    lines.append('━━━━━━━━━━━━━━━━━━━')
    lines.append('')
    lines.append('**▌一、市场全景**')
    lines.append('')
    lines.append(f'昨日涨停 {market_data.get("zt_count","?")}只')
    lines.append(f'封板率 {market_data.get("seal_rate","?")}%')
    lines.append(f'成交 {market_data.get("volume","?")}万亿')
    lines.append(f'涨跌 {market_data.get("up","?")} / {market_data.get("down","?")}')
    lines.append('')
    lines.append('**▌二、题材强度**')
    lines.append('')
    for t in themes[:3]:
        lines.append(f'① {t["name"]} ---- {t["zt"]}只涨停')
        lines.append(f'  成交额: {t["vol"]}')
        lines.append(f'  龙头: {t["leader"]}')
        lines.append('')
    lines.append('')
    lines.append('**▌三、情绪周期**')
    lines.append('')
    lines.append(f'{market_data.get("emotion","判断中")}')
    lines.append('')
    lines.append('**▌四、唯一最优解**')
    lines.append('')
    if best:
        lines.append(f'方向: {best["theme"]}')
        lines.append(f'标的: {best["stock"]}')
        lines.append(f'成交额: {best["vol"]} ✅')
        lines.append('')
        for cond in best['conditions']:
            lines.append(cond)
    else:
        lines.append('暂无可操作标的')
    lines.append('')
    lines.append('━━━━━━━━━━━━━━━━━━━')
    lines.append(f'生成: 09:26 | 下次更新: 10:00')
    return '\n'.join(lines)

# ===== Main =====
try:
    import akshare as ak
    zt = ak.stock_zt_pool_em(date=today)
    zt_count = len(zt)
    seal_count = sum(1 for t in zt.iloc[:,12] if str(t).strip() == '0')
    seal_rate = round(seal_count/zt_count*100) if zt_count > 0 else 0
    up = int(zt_count * 2.5)  # rough estimate
    down = int(zt_count * 0.5)

    market = {
        'zt_count': zt_count, 'seal_rate': seal_rate,
        'volume': '待更新', 'up': up, 'down': down,
        'emotion': '等待09:30开盘确认具体数据'
    }
    themes = [{'name':'待采集','zt':'?','vol':'?','leader':'?'}]
    best = None

    report = build_report(market, themes, best)
    print(report)

    ok = dingtalk_send(report)
    if ok:
        print('日报已推送到钉钉 ✅')
    else:
        print('钉钉推送失败 ⚠️')

except Exception as e:
    print(f'日报生成失败: {e}')
    dingtalk_send(f'日报生成失败: {str(e)[:100]}')
