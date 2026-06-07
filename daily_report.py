"""
每日盘前日报 v2.0 - 09:26 自动生成 -> 钉钉推送
重构: 列索引常量、统一过滤、模板化输出
"""
import os, sys, requests, time, hmac, hashlib, base64, urllib.parse
from datetime import datetime, timedelta
try: sys.stdout.reconfigure(encoding='utf-8')
except: pass

# ===== 常量 =====
TOKEN = os.environ.get('DINGTALK_TOKEN', 'd69ad254111dd477bbb8fe8ee1f754908f88a83ff21f4daec25b5ce6365103fc')
SECRET = os.environ.get('DINGTALK_SECRET', 'SECc3449095eb18f883114db609ea5c8421035351356772b5bdb92248fe162b6293')
MIN_VOL = 1e8       # 成交量最低阈值
MIN_BID = 500e4     # 竞价成交额最低阈值
HIGH_TURN = 10      # 高换手阈值(承托判断)

# 涨停池列索引
COL = {
    'rank': 0, 'code': 1, 'name': 2, 'pct': 3, 'price': 4,
    'vol': 5, 'mcap': 6, 'tcap': 7, 'turn': 8, 'seal': 9,
    'ftime': 10, 'ltime': 11, 'zb': 12, 'lb': 13, 'lb2': 14, 'reason': 15
}

# ===== 工具函数 =====
def row(r, idx):
    """安全读取行数据"""
    try: return r.iloc[idx]
    except: return ''

def valid_name(name):
    return not (name.startswith('*') or 'ST' in name or '退' in name)

def is_valid(row_data):
    name = str(row_data[COL['name']])
    vol = safe_float(row_data[COL['vol']])
    return valid_name(name) and vol >= MIN_VOL

def safe_float(val, default=0):
    try: return float(val) if val else default
    except: return default

def safe_int(val, default=0):
    try: return int(float(val)) if val else default
    except: return default

def dingtalk_send(text):
    ts = str(round(time.time() * 1000))
    sign = base64.b64encode(hmac.new(SECRET.encode(), f'{ts}\n{SECRET}'.encode(), hashlib.sha256).digest()).decode()
    url = f'https://oapi.dingtalk.com/robot/send?access_token={TOKEN}&timestamp={ts}&sign={urllib.parse.quote_plus(sign)}'
    try:
        r = requests.post(url, json={'msgtype':'markdown','markdown':{'title':'盘前日报','text':text}}, timeout=10)
        return r.ok
    except: return False

def get_last_trade_day():
    """获取最近交易日"""
    d = datetime.now()
    return (d - timedelta(days=3 if d.weekday() == 0 else (2 if d.weekday() == 6 else 1))).strftime('%Y%m%d')

# ===== 获取数据 =====
date_used = get_last_trade_day()
zt, source = None, '无数据'
try:
    import akshare as ak
    zt = ak.stock_zt_pool_em(date=date_used)
    if zt is not None and len(zt) > 0: source = 'akshare'
except: pass

# ===== 构建日报 =====
L = []  # lines
L.append(f'## 盘前日报 {date_used} ({["周一","周二","周三","周四","周五","周六","周日"][datetime.now().weekday()]})')
L.append(''); L.append('------')

if zt is None:
    L.append(''); L.append('昨日行情数据暂不可用'); L.append('')
else:
    zt_count = len(zt)

    # 》》》 一、市场全景《《《
    early = sum(1 for t in zt.iloc[:,COL['ftime']] if str(t)[:4] <= '1000')
    sealed = sum(1 for t in zt.iloc[:,COL['zb']] if str(t).strip() in ['0', '0.0'])
    seal_rate = round(sealed/zt_count*100) if zt_count > 0 else 0
    L.append(''); L.append('**一、市场全景**'); L.append('')
    L.append(f'涨停{zt_count}只 | 早盘封板{early}只 | 封板率{seal_rate}%')
    L.append(f'数据源: {source}'); L.append('')

    # 》》》 二、题材强度《《《
    L.append('**二、题材强度**'); L.append('')
    rows = [zt.iloc[i].tolist() for i in range(len(zt))]
    concepts = {}
    for r in rows:
        if not is_valid(r): continue
        reason = str(r[COL['reason']])[:20]
        vol = safe_float(r[COL['vol']])
        tag = reason.split('+')[0].strip()[:10] if '+' in reason else reason[:8]
        if len(tag) < 2: continue
        if tag not in concepts: concepts[tag] = {'cnt':0, 'vol':0, 'lbs':[], 'bigs':[]}
        concepts[tag]['cnt'] += 1
        concepts[tag]['vol'] += vol
        lb = str(r[COL['lb']])
        if len(lb) > 2: concepts[tag]['lbs'].append(str(r[COL['name']]) + '(' + lb + ')')
        if vol >= 20e8: concepts[tag]['bigs'].append(str(r[COL['name']]))

    for tag, data in sorted(concepts.items(), key=lambda x: -x[1]['cnt'])[:4]:
        L.append(f'{tag} -- {data["cnt"]}只涨停 (成交{data["vol"]/1e8:.0f}亿)')
        if data['lbs']: L.append(f'  连板: {" ".join(data["lbs"][:3])}')
        if data['bigs']: L.append(f'  大量: {" ".join(data["bigs"][:3])}')
        # 一日游判断
        if not data['lbs'] and data['vol'] < 30e8:
            L.append('  ⚠️ 无连板+成交小 → 一日游概率大')
        L.append('')

    # 》》》 三、弱转强候选《《《
    L.append('**三、弱转强候选**'); L.append('')
    try:
        import pywencai
        df_bid = pywencai.get(question=f'{datetime.now().strftime("%Y%m%d")} 竞价成交额 竞价涨跌幅 非ST', perpage=100)
        bid_map = {}
        for i in range(len(df_bid)):
            try:
                code = str(df_bid.iloc[i][0])
                for c in range(len(df_bid.columns)):
                    if '竞价' in str(df_bid.columns[c]) and '额' in str(df_bid.columns[c]):
                        v = safe_float(df_bid.iloc[i][c]) if df_bid.iloc[i][c] else 0
                        if v > 0: bid_map[code] = v
                        break
            except: pass
    except:
        bid_map = {}

    wts = []
    for r in rows:
        if not is_valid(r): continue
        zb = str(r[COL['zb']]).strip()
        if zb in ['0', '0.0', '']: continue

        turn = safe_float(r[COL['turn']])
        bid_v = bid_map.get(str(r[COL['code']]), 0)

        score = (1 if turn > HIGH_TURN else 0) + (2 if bid_v > MIN_BID else 0) + (1 if safe_int(zb) <= 3 else 0)
        if score > 0:
            wts.append((
                str(r[COL['name']]),
                safe_float(r[COL['vol']]),
                safe_int(zb), score, bid_v,
                turn > HIGH_TURN, bid_v > MIN_BID,
                str(r[COL['reason']])[:25]
            ))

    wts.sort(key=lambda x: -x[3])
    if wts:
        for name, vol, zb, sc, bid, sup, b_s, reason in wts[:5]:
            tags = []
            if sup: tags.append('承托')
            if b_s: tags.append('竞价放量')
            L.append(f'{name} 量{vol/1e8:.0f}亿 炸板{zb}次 {"+".join(tags)} [{reason}]')
    else:
        L.append('暂无符合条件的标的')
    L.append('')

    # 》》》 四、连板梯队《《《
    L.append('**四、连板梯队**'); L.append('')
    lbs = []
    for r in rows:
        if not is_valid(r): continue
        info = str(r[COL['lb']])
        if len(info) > 2: lbs.append((str(r[COL['name']]), info))
    if lbs:
        for name, info in lbs[:8]:
            L.append(f'{name} ({info})')
    else:
        L.append('无连板')
    L.append('')

# 》》》 五、操作策略《《《
L.append('**五、操作策略**'); L.append('')
L.append('09:25竞价 → 弱转强高开关注')
L.append('09:30-10:00 → 转强买入,转弱放弃')
L.append('成交量<1亿、ST不参与'); L.append('')
L.append('------')
L.append(f'{date_used}数据 | 推送09:26')

report = '\n'.join(L)
print(report)
ok = dingtalk_send(report)
print('#' + ('推送成功' if ok else '推送失败'))
