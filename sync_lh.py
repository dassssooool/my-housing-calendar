"""Fetch LH public housing notices using the approved data.go.kr service.
Only publication dates are shown as publication events: application periods require a separate verified source.
Never store the API key in the repository.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request

URL = "https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1"
KEY = os.environ.get("LH_API_KEY", "").strip()
if not KEY:
    raise SystemExit("LH_API_KEY GitHub Actions secret is missing")
TODAY = dt.date.today()
START = TODAY - dt.timedelta(days=120)
END = TODAY + dt.timedelta(days=60)

def normalize_date(value):
    if not value:
        return ""
    value = str(value).strip().replace(".", "-").replace("/", "-")
    if len(value) >= 10:
        value = value[:10]
    elif len(value) == 8 and value.isdigit():
        value = value[:4] + "-" + value[4:6] + "-" + value[6:]
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        return ""

def rows_from(data):
    """Walk LH's nested dsSch/dsList response without mistaking wrappers for notices."""
    found = []
    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            keys = {str(k).upper() for k in value}
            if "PAN_NM" in keys or "PAN_ID" in keys:
                found.append(value)
            else:
                for item in value.values():
                    if isinstance(item, (list, dict)):
                        visit(item)
    visit(data)
    return found

def get_page(category, page):
    params = {
        "ServiceKey": KEY,
        "PG_SZ": "100",
        "PAGE": str(page),
        "UPP_AIS_TP_CD": category,
        "PAN_NT_ST_DT": START.strftime("%Y.%m.%d"),
        "CLSG_DT": END.strftime("%Y.%m.%d"),
    }
    req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": "HousingCalendar/1.1"})
    with urllib.request.urlopen(req, timeout=35) as resp:
        raw = resp.read()
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError("LH API did not return JSON: " + raw[:160].decode("utf-8", "replace")) from exc
    if isinstance(data, dict):
        if str(data.get("SS_CODE", "Y")).upper() not in ("Y", "00", "SUCCESS"):
            raise RuntimeError("LH API returned an error: " + str(data)[:250])
        for key in ("resHeader", "header"):
            header = data.get(key)
            if isinstance(header, dict) and str(header.get("SS_CODE", "Y")).upper() not in ("Y", "00", "SUCCESS"):
                raise RuntimeError("LH API returned an error: " + str(header)[:250])
    rows = rows_from(data)
    if page == 1:
        print(f"LH category={category}: rows={len(rows)}; top-level keys={list(data)[:12] if isinstance(data, dict) else type(data).__name__}; sample fields={list(rows[0])[:25] if rows else []}; dsSch shape={[(list(v)[:12] if isinstance(v,dict) else type(v).__name__) for v in data.get('dsSch',[])[:2]] if isinstance(data,dict) and isinstance(data.get('dsSch'),list) else 'n/a'}")
    return rows

def infer_targets(title, kind="", broad=""):
    """Keyword-based discovery tags, not an eligibility determination."""
    text = " ".join((title, kind, broad))
    targets = []
    if any(word in text for word in ("신혼", "신생아", "예비신혼")):
        targets.append("신혼부부")
    if any(word in text for word in ("청년", "대학생", "사회초년생")):
        targets.append("청년")
    if any(word in text for word in ("일반", "국민임대", "통합공공임대", "공공분양", "10년공공임대", "10년 분양전환", "영구임대")):
        targets.append("일반공급")
    if "생애최초" in text:
        targets.append("생애최초")
    return targets

def make_notice(row):
    title = str(row.get("PAN_NM") or "").strip()
    area = str(row.get("CNP_CD_NM") or "").strip()
    if not title:
        return None
    if "서울" in area or area == "11":
        region = "서울"
    elif "경기" in area or area == "41":
        region = "경기"
    elif area in ("전국", "전체", ""):
        region = "서울" if "서울" in title else "경기" if "경기" in title else None
    else:
        return None
    if not region:
        return None
    kind = str(row.get("AIS_TP_CD_NM") or "").strip()
    broad = str(row.get("UPP_AIS_TP_NM") or "").strip()
    combined = title + " " + kind + " " + broad
    if any(k in combined for k in ("상가", "토지", "주차장")):
        return None
    if any(k in combined for k in ("분양", "신혼희망타운")) and not any(k in combined for k in ("임대", "전세", "행복주택")):
        typ = "공공분양"
    else:
        typ = "공공임대"
    posted = normalize_date(row.get("PAN_NT_ST_DT") or row.get("PAN_NT_DT") or row.get("PAN_DT"))
    if not posted:
        return None
    link = str(row.get("DTL_URL") or "").strip()
    if not link.startswith(("https://", "http://")):
        link = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do?mi=1026"
    stable = str(row.get("PAN_ID") or row.get("PAN_NO") or link + title)
    uid = hashlib.sha256(stable.encode()).hexdigest()[:18]
    return {
        "id": "LH-" + uid,
        "title": title,
        "agency": "LH",
        "region": region,
        "type": typ,
        "targets": infer_targets(title, kind, broad),
        "start": posted,
        "end": posted,
        "eventKind": "publication",
        "detailUrl": link,
        "memo": "LH 공식 공고 게시일입니다. 청약 접수 시작·마감일이 아닙니다. 접수 일정과 신청자격은 반드시 공식 공고문에서 확인하세요. 세부유형: " + (kind or "미확인"),
        "isSample": False,
    }

def main():
    notices = {}
    counts = {"raw": 0, "usable": 0}
    for category in ("06", "13", "05", "39"):
        for page in range(1, 11):
            chunk = get_page(category, page)
            counts["raw"] += len(chunk)
            for row in chunk:
                notice = make_notice(row)
                if notice:
                    notices[notice["id"]] = notice
                    counts["usable"] += 1
            if len(chunk) < 100:
                break
    print(f"LH diagnostic: {counts}")
    if not notices:
        print("WARNING: LH returned no usable Seoul/Gyeonggi notices. Existing LH data preserved.")
        return
    output = Path(__file__).with_name("lh_notices.json")
    output.write_text(json.dumps({"entries": sorted(notices.values(), key=lambda n: n["start"])}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"LH public notices: {len(notices)} publication events")

if __name__ == "__main__":
    main()
