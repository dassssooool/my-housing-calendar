"""Import SH public rental announcements from the Seoul Housing Portal."""
import datetime
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

BASE = "https://housing.seoul.go.kr/site/main/sh/publicLease"
CATEGORIES = ("02", "03", "04", "05", "06", "07", "10", "11", "13", "14", "20", "23")


class NoticeList(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.cells = None
        self.cell = None
        self.link = ""
        self.pages = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.cells, self.link = [], ""
        elif tag == "td" and self.cells is not None:
            self.cell = []
        elif tag == "a":
            url = attrs.get("href", "")
            parsed = urlsplit(url)
            query = parse_qs(parsed.query)
            if attrs.get("title") == "마지막 페이지" and "cp" in query:
                self.pages = int(query["cp"][0])
            if (self.cells is not None and parsed.scheme == "https"
                    and parsed.hostname in ("www.i-sh.co.kr", "i-sh.co.kr")
                    and parsed.path.endswith("/view.do") and "seq" in query):
                self.link = url

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.cells.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.cells is not None:
            if self.link and len(self.cells) >= 8:
                self.rows.append((self.cells, self.link))
            self.cells = None


def load_page(category, page):
    url = f"{BASE}/{category}/list?cp={page}&supplyType=publicLease&splyCd={category}"
    with urlopen(Request(url, headers={"User-Agent": "HousingCalendar/1.1"}), timeout=30) as response:
        html = response.read().decode("utf-8")
    parsed = NoticeList()
    parsed.feed(html)
    if parsed.pages is None and "공고게시일" not in html:
        raise ValueError(f"Unexpected SH listing for category {category}")
    return parsed


def collect():
    notices = {}
    for category in CATEGORIES:
        first = load_page(category, 1)
        for page in range(1, (first.pages or 1) + 1):
            listing = first if page == 1 else load_page(category, page)
            for cells, link in listing.rows:
                _, kind, title, posted, *_ = cells
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", posted):
                    continue
                datetime.date.fromisoformat(posted)
                seq = parse_qs(urlsplit(link).query)["seq"][0]
                targets = [tag for tag, terms in (
                    ("신혼부부", ("신혼", "신생아")),
                    ("청년", ("청년", "대학생")),
                    ("일반공급", ("일반공급",)),
                ) if any(term in title for term in terms)]
                notices[seq] = {
                    "id": f"SH-{seq}", "title": title, "agency": "SH",
                    "region": "서울", "type": "공공임대", "targets": targets,
                    "start": posted, "end": posted, "eventKind": "publication",
                    "dateSource": "서울주거포털 공고게시일", "detailUrl": link,
                    "memo": f"세부유형: {kind}. 접수 일정과 대상은 SH 공식 공고문에서 확인하세요.",
                    "isSample": False,
                }
    if not notices:
        raise RuntimeError("SH listing returned no usable notices")
    return list(notices.values())


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("notices.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    sh = collect()
    data["entries"] = sorted(
        [notice for notice in data["entries"] if notice.get("agency") != "SH"] + sh,
        key=lambda notice: notice["start"],
    )
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SH announcements merged: {len(sh)}")


if __name__ == "__main__":
    main()
