"""청약홈 공고 조회 -> 기존 캘린더에서 가져올 수 있는 JSON 생성.
Usage: APPLYHOME_API_KEY=... python sync_applyhome.py
인증키를 파일에 쓰지 않고 환경변수로 전달합니다.
"""
import json, os, urllib.parse, urllib.request, datetime, pathlib, time

BASE='https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/'
ENDPOINTS={
 'APT':'getAPTLttotPblancDetail',
 '오피스텔·도시형·민간임대':'getUrbtyOfctlLttotPblancDetail',
 '잔여세대':'getRemndrLttotPblancDetail',
}
KEY=os.environ.get('APPLYHOME_API_KEY','').strip()
if not KEY: raise SystemExit('환경변수 APPLYHOME_API_KEY가 필요합니다. 인증키를 코드에 넣지 마세요.')
TODAY=datetime.date.today()
SINCE=(TODAY-datetime.timedelta(days=100)).isoformat()
REGIONS=('서울','경기','인천')

def get_rows(endpoint):
    rows=[]
    for page in range(1,11):
        params={'serviceKey':KEY,'page':page,'perPage':100,'returnType':'JSON', 'cond[RCRIT_PBLANC_DE::GTE]':SINCE}
        url=BASE+endpoint+'?'+urllib.parse.urlencode(params)
        req=urllib.request.Request(url,headers={'User-Agent':'PersonalHousingCalendar/1.0'})
        with urllib.request.urlopen(req,timeout=25) as r: data=json.load(r)
        if not isinstance(data,dict) or not isinstance(data.get('data'),list):
            raise ValueError(f'예상하지 못한 응답: {str(data)[:250]}')
        chunk=data['data']
        if page==1: print(f'청약홈 API {endpoint}: totalCount={data.get("totalCount")}, currentCount={data.get("currentCount")}, 조건={SINCE}, 응답키={list(data)[:12]}')
        rows.extend(chunk)
        if len(chunk)<100:break
        time.sleep(.15)
    return rows

def date(x):
    if not x:return ''
    s=str(x).strip()[:10]
    if len(s)==8 and s.isdigit():s=f'{s[:4]}-{s[4:6]}-{s[6:]}'
    try:return datetime.date.fromisoformat(s).isoformat()
    except ValueError:return ''

def make_notice(row,kind):
    area=str(row.get('SUBSCRPT_AREA_CODE_NM') or '')
    address=str(row.get('HSSPLY_ADRES') or '')
    region=next((r for r in REGIONS if r in area or r in address),None)
    if not region:return None
    start=date(row.get('RCEPT_BGNDE') or row.get('SPSPLY_RCEPT_BGNDE') or row.get('SUBSCRPT_RCEPT_BGNDE') or row.get('GNRL_RCEPT_BGNDE'))
    end=date(row.get('RCEPT_ENDDE') or row.get('GNRL_RCEPT_ENDDE') or row.get('SPSPLY_RCEPT_ENDDE') or row.get('SUBSCRPT_RCEPT_ENDDE'))
    if not start or not end or end<start:return None
    house=str(row.get('HOUSE_NM') or '주택명 미확인')
    no=str(row.get('HOUSE_MANAGE_NO') or '')+'-'+str(row.get('PBLANC_NO') or '')
    targets=['일반공급']
    if row.get('SPSPLY_HSHLDCO') not in (None,'',0,'0'):targets.extend(['신혼부부','생애최초'])
    if kind=='APT' and '신혼' in house:targets.append('신혼부부')
    if '청년' in house:targets.append('청년')
    link=str(row.get('HMPG_ADRES') or '').strip()
    if link and not link.startswith(('https://','http://')):link=''
    return {'id':'APPLYHOME-'+kind+'-'+no,'title':house,'agency':'청약홈','region':region,
            'type':'민간분양' if kind!='오피스텔·도시형·민간임대' else '민간임대',
            'targets':list(dict.fromkeys(targets)),'start':start,'end':end,
            'detailUrl':link,'memo':f'청약홈 API · {kind} · 모집공고일 {row.get("RCRIT_PBLANC_DE", "미확인")}. 대상별 공급자격은 반드시 원문 확인.',
            'isSample':False}

notices={};errors=[]
raw_counts={};valid_counts={};sample_keys={};reject_counts={}
for kind,endpoint in ENDPOINTS.items():
    try:
        rows=get_rows(endpoint)
        raw_counts[kind]=len(rows)
        sample_keys[kind]=list(rows[0])[:35] if rows else []
        valid_counts[kind]=0
        reject_counts[kind]={'region':0,'dates':0}
        for row in rows:
            n=make_notice(row,kind)
            if n:
                notices[n['id']]=n
                valid_counts[kind]+=1
            else:
                area=str(row.get('SUBSCRPT_AREA_CODE_NM') or '')
                address=str(row.get('HSSPLY_ADRES') or '')
                if not any(r in area or r in address for r in REGIONS):
                    reject_counts[kind]['region']+=1
                else:
                    reject_counts[kind]['dates']+=1
    except Exception as e:errors.append(f'{kind}: {e}')
print('청약홈 진단: 원본 건수=',raw_counts,'달력 반영 건수=',valid_counts,'제외 사유=',reject_counts)
print('청약홈 응답 필드명=',sample_keys)
if errors:raise SystemExit('일부 조회 실패. 기존 데이터를 덮어쓰지 않았습니다.\n'+'\n'.join(errors))
# Do not overwrite existing published Applyhome notices with an empty result
# until the API response/filter mismatch is diagnosed.
existing_path=pathlib.Path(__file__).with_name('notices.json')
if not any(valid_counts.values()) and existing_path.exists():
    old=json.loads(existing_path.read_text(encoding='utf-8'))
    preserved=[n for n in old.get('entries',[]) if isinstance(n,dict) and n.get('agency')=='청약홈']
    for n in preserved:
        notices[n['id']]=n
    print(f'청약홈 0건: 기존 청약홈 데이터 {len(preserved)}건 보존')
# Merge successfully fetched LH notices; do not invent application dates.
lh_path=pathlib.Path(__file__).with_name('lh_notices.json')
if lh_path.exists():
    lh_data=json.loads(lh_path.read_text(encoding='utf-8'))
    for n in lh_data.get('entries',[]):
        if isinstance(n,dict) and n.get('agency')=='LH' and n.get('id'):
            notices[n['id']]=n
out={'schemaVersion':1,'exportedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
     'entries':sorted(notices.values(),key=lambda x:x['start']),'favorites':[]}
path=pathlib.Path(__file__).with_name('notices.json')
path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'{len(notices)}건 저장: {path.name}. 캘린더에서 JSON 가져오기를 누르세요.')
