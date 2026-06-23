#!/usr/bin/env python3
"""
Weekly regulatory newsletter generator for FITI 화학바이오본부.
Fetches latest news from regulatory RSS feeds and generates HTML via Claude API.
"""

import os
import sys
import datetime
import urllib.request
import xml.etree.ElementTree as ET

import anthropic

# ---------------------------------------------------------------------------
# RSS feeds from key regulatory bodies
# ---------------------------------------------------------------------------
RSS_FEEDS = {
    "FDA Press Announcements": (
        "https://www.fda.gov/about-fda/contact-fda/stay-informed"
        "/rss-feeds/pressannouncements/rss.xml"
    ),
    "EPA Newsroom": "https://www.epa.gov/newsroom/rss.xml",
    "Federal Register (FDA)": (
        "https://www.federalregister.gov/api/v1/articles.rss"
        "?conditions[agencies][]=food-and-drug-administration"
        "&conditions[type][]=Rule&conditions[type][]=Proposed+Rule"
    ),
    "ECHA News": "https://echa.europa.eu/rss/news.xml",
    "EMA News": "https://www.ema.europa.eu/en/news-events/news/rss",
}

KEYWORDS = [
    "PFAS", "extractable", "leachable", "E&L", "NIAS",
    "packaging", "food contact", "biopharmaceutical",
    "single-use", "USP", "ICH", "REACH", "규제",
]


def _parse_ns(tag: str, ns: dict) -> str:
    """Helper to format a namespaced tag."""
    prefix, local = tag.split(":", 1) if ":" in tag else ("", tag)
    uri = ns.get(prefix, "")
    return f"{{{uri}}}{local}" if uri else local


def fetch_rss(source_name: str, url: str, max_items: int = 8) -> list[dict]:
    """Fetch an RSS/Atom feed and return a list of article dicts."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FITI-NewsBot/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except Exception as exc:
        print(f"  [WARN] {source_name}: {exc}", file=sys.stderr)
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        print(f"  [WARN] {source_name} XML parse error: {exc}", file=sys.stderr)
        return []

    items = []
    atom_ns = "http://www.w3.org/2005/Atom"

    # --- RSS 2.0 ---
    for el in root.findall(".//item")[:max_items]:
        title = (el.findtext("title") or "").strip()
        desc = (el.findtext("description") or "").strip()
        link = (el.findtext("link") or "").strip()
        if title:
            items.append({"source": source_name, "title": title, "desc": desc, "link": link})

    # --- Atom 1.0 ---
    if not items:
        ns = {"a": atom_ns}
        for el in root.findall(f"a:entry", ns)[:max_items]:
            title = (el.findtext("a:title", namespaces=ns) or "").strip()
            summary = (el.findtext("a:summary", namespaces=ns) or "").strip()
            link_el = el.find("a:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            if title:
                items.append({"source": source_name, "title": title, "desc": summary, "link": link})

    return items


def is_relevant(item: dict) -> bool:
    """Rough keyword filter — keep items likely related to chemical/bio regulations."""
    text = (item["title"] + " " + item["desc"]).lower()
    return any(kw.lower() in text for kw in KEYWORDS)


def build_context(all_items: list[dict]) -> str:
    """Build a text block of news items for the Claude prompt."""
    if not all_items:
        return "※ RSS 피드 수집 실패 — Claude 학습 데이터 기반으로 최신 동향 요약"

    lines = []
    for item in all_items:
        link_part = f"\n   링크: {item['link']}" if item["link"] else ""
        lines.append(
            f"[{item['source']}]\n"
            f"제목: {item['title']}\n"
            f"내용: {item['desc'][:300]}{link_part}"
        )
    return "\n\n".join(lines)


def generate_newsletter(news_context: str, date_str: str) -> str:
    """Call Claude API to generate the full HTML newsletter."""
    client = anthropic.Anthropic()

    system = (
        "당신은 FITI시험연구원 화학바이오본부의 AI 규제 리서치 어시스턴트입니다.\n"
        "임직원을 위해 매주 화학·바이오 규제동향 뉴스레터 HTML을 생성합니다.\n"
        "반드시 완전한 standalone HTML 파일을 출력하세요 (코드 블록 없이 순수 HTML만)."
    )

    user = f"""오늘 날짜: {date_str}

다음은 주요 규제 기관 RSS에서 수집한 이번 주 최신 뉴스입니다:

{news_context}

위 뉴스를 참고하여 주간 규제동향 뉴스레터 HTML을 작성해주세요.

[뉴스레터 구조 — 6개 섹션]
1. 🧬 바이오의약품 E&L (USP, ICH Q3E, EMA, FDA 관련)
2. ⚗️ 포장재 NIAS (EU FCM 규정, 식품접촉물질)
3. ⚠️ PFAS 글로벌 규제 (EU PPWR, ECHA REACH, EPA, 한국)
4. 🏛️ 유관기관 동향 (KTR, KCL, KATRI, KOTITI)
5. 🏢 정부 세미나·행사 (식약처, 환경부, 산업부)
6. 💡 FITI 시사점 (화학바이오본부 전략적 대응 포인트 3개)

[HTML 디자인 요구사항]
- 다크 테마: 배경 #0f1923, 카드 #1a2736, 텍스트 #e0e6ed
- 아코디언 섹션 (onclick 토글, CSS max-height 트랜지션)
- 뱃지: 긴급(빨강/badge-urgent), 주의(노랑/badge-caution), 참고(초록/badge-info)
- 섹션 헤더: 아이콘(48px 그라디언트 원형) + 제목 + 건수 배지 + 화살표
- 모바일 반응형 (@media max-width:600px)
- 출처 링크 포함 (target="_blank")
- 푸터: "FITI시험연구원 화학바이오본부 | 매주 금요일 자동 발행"
- 상단 레이블: "WEEKLY REGULATORY BRIEF"

완전한 HTML 파일을 출력하세요. ```html 블록 없이 <!DOCTYPE html>부터 시작하세요."""

    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=8192,
        messages=[{"role": "user", "content": user}],
        system=system,
    )

    html = message.content[0].text.strip()

    # Strip code fences if model added them
    for fence in ("```html", "```"):
        if html.startswith(fence):
            html = html[len(fence):]
    if html.endswith("```"):
        html = html[:-3]

    return html.strip()


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    today = datetime.date.today()
    date_str = today.strftime("%Y.%m.%d")
    print(f"Generating newsletter for {date_str} ...")

    # Collect news from all feeds
    all_items: list[dict] = []
    for source_name, url in RSS_FEEDS.items():
        print(f"  Fetching {source_name} ...", end=" ", flush=True)
        items = fetch_rss(source_name, url)
        relevant = [i for i in items if is_relevant(i)]
        print(f"{len(relevant)} relevant items (of {len(items)} fetched)")
        all_items.extend(relevant)

    print(f"Total relevant items: {len(all_items)}")

    news_context = build_context(all_items)

    print("Calling Claude API ...")
    html = generate_newsletter(news_context, date_str)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Saved: {out_path}  ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
