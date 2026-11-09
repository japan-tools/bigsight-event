"""
Tokyo Big Sight Event Scraper
Scrapes event listings from https://www.bigsight.jp/visitor/event/search.php
Saves results to events.json (English keys) and events.csv (Japanese headers)

HTML structure (confirmed):
  <article class="lyt-event-01">
    <h3 class="hdg-01"><a href="EVENT_URL">EVENT_NAME</a></h3>
    <div class="lyt-img-02">
      <div class="img"><img src="/visitor/event/img/thumbnail/..."/></div>
      <div class="content">
        <dl class="list-01">  <- 入場区分, 利用施設, 開催期間, 開催時間, 料金, URL
      </div>
    </div>
    <div class="lyt-box-01">
      <dl class="list-02">  <- 主催者, 連絡先
    </div>
  </article>
"""

import csv
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://www.bigsight.jp"
SEARCH_URL = "https://www.bigsight.jp/visitor/event/search.php"
JSON_FILE = "events.json"
CSV_FILE = "events.csv"
MD_FILE = "events.md"
REQUEST_DELAY = 1.0

# English key → Japanese CSV header (order defines column order)
FIELD_MAP = [
    ("event_name",    "イベント名"),
    ("event_url",     "イベントURL"),
    ("admission_type", "入場区分"),
    ("venue",         "利用施設"),
    ("period",        "開催期間"),
    ("hours",         "開催時間"),
    ("admission_fee", "料金"),
    ("organizer",     "主催者"),
    ("contact",       "連絡先"),
    ("logo_url",      "イベントロゴURL"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
}


def fetch_page(url: str, params: dict = None) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"  [ERROR] {url} -> {e}")
        return None


def parse_dl(dl_tag) -> dict:
    """Parse a dl tag with div>dt+dd structure into a dict."""
    result = {}
    if dl_tag is None:
        return result
    for div in dl_tag.find_all("div"):
        dt = div.find("dt")
        dd = div.find("dd")
        if dt and dd:
            for svg in dd.find_all("svg"):
                svg.decompose()
            key = dt.get_text(strip=True)
            value = dd.get_text(separator="\n", strip=True)
            result[key] = value
    return result


def parse_event(article) -> dict:
    """Parse a single <article class='lyt-event-01'> into a flat dict with English keys."""
    h3 = article.find("h3", class_="hdg-01")
    a_tag = h3.find("a") if h3 else None
    if a_tag:
        for svg in a_tag.find_all("svg"):
            svg.decompose()
    event_name = a_tag.get_text(strip=True) if a_tag else ""
    event_url = a_tag.get("href", "") if a_tag else ""

    img_div = article.find("div", class_="img")
    img_tag = img_div.find("img") if img_div else None
    logo_url = ""
    if img_tag:
        src = img_tag.get("src", "")
        logo_url = urljoin(BASE_URL, src) if src else ""

    dl1 = article.find("dl", class_="list-01")
    fields1 = parse_dl(dl1)

    dl2 = article.find("dl", class_="list-02")
    fields2 = parse_dl(dl2)

    return {
        "event_name":     event_name,
        "event_url":      fields1.get("URL", event_url),
        "admission_type": fields1.get("入場区分", ""),
        "venue":          fields1.get("利用施設", ""),
        "period":         fields1.get("開催期間", ""),
        "hours":          fields1.get("開催時間", ""),
        "admission_fee":  fields1.get("料金", ""),
        "organizer":      fields2.get("主催者", "") or fields2.get("開催者", ""),
        "contact":        fields2.get("連絡先", ""),
        "logo_url":       logo_url,
    }


def scrape_all_events() -> list:
    all_events = []
    page = 1

    print("Tokyo Big Sight event scraping started...")

    while True:
        print(f"  Fetching page {page}...")
        soup = fetch_page(SEARCH_URL, params={"page": page})

        if soup is None:
            print(f"  Failed to fetch page {page}, stopping.")
            break

        articles = soup.find_all("article", class_="lyt-event-01")

        if not articles:
            print(f"  No events on page {page}, stopping.")
            break

        for article in articles:
            ev = parse_event(article)
            if ev["event_name"]:
                all_events.append(ev)

        print(f"  {len(articles)} events (total: {len(all_events)})")

        next_link = soup.select_one("p.next a.next[href]")
        if not next_link:
            print("  Last page reached.")
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    return all_events


def save_json(events: list) -> None:
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    print(f"JSON saved → {JSON_FILE}")


def save_csv(events: list) -> None:
    en_keys = [k for k, _ in FIELD_MAP]
    ja_headers = ["No"] + [h for _, h in FIELD_MAP]

    with open(CSV_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(ja_headers)
        for i, ev in enumerate(events, 1):
            row = [i] + [ev.get(k, "").replace("\n", " ") for k in en_keys]
            writer.writerow(row)

    print(f"CSV  saved → {CSV_FILE}")


def save_md(events: list) -> None:
    # event_url is merged into event_name; exclude it from its own column
    md_fields = [(k, h) for k, h in FIELD_MAP if k != "event_url"]
    ja_headers = [h for _, h in md_fields]
    en_keys = [k for k, _ in md_fields]

    with open(MD_FILE, "w", encoding="utf-8") as f:
        f.write("# Tokyo Big Sight イベント一覧\n\n")

        f.write("| No | " + " | ".join(ja_headers) + " |\n")
        f.write("| " + " | ".join(["---"] * (len(ja_headers) + 1)) + " |\n")

        for i, ev in enumerate(events, 1):
            cells = []
            for key in en_keys:
                val = ev.get(key, "").replace("\n", " ").replace("|", "｜")
                if key == "event_name":
                    url = ev.get("event_url", "")
                    val = f"[{val}]({url})" if url else val
                elif key == "logo_url" and val:
                    val = f"![]({val})"
                cells.append(val)
            f.write(f"| {i} | " + " | ".join(cells) + " |\n")

    print(f"MD   saved → {MD_FILE}")


def main():
    events = scrape_all_events()
    print(f"\nTotal: {len(events)} events collected.")

    save_json(events)
    save_csv(events)
    save_md(events)

    if events:
        print("\n--- Sample (first event) ---")
        print(json.dumps(events[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
