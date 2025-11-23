update_feed.py
import os
import re
import requests
from urllib.parse import urljoin
from datetime import datetime
from email.utils import format_datetime
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

ORAL_ARGUMENT_INDEX = "https://cafc.uscourts.gov/home/oral-argument/listen-to-oral-arguments/"
FEED_PATH = "feed.xml"
PODCAST_BASE_URL = "https://sneha-s2003.github.io/Federal-Circuit"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "Federal-Circuit-Podcast-Bot/1.0"

def fetch_html(url: str) -> str:
    resp = SESSION.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text

def discover_mp3_links() -> list[dict]:
    html = fetch_html(ORAL_ARGUMENT_INDEX)
    soup = BeautifulSoup(html, "html.parser")
    cases = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".mp3"):
            mp3_url = urljoin(ORAL_ARGUMENT_INDEX, href)
            text = a.get_text(strip=True)

            filename = os.path.basename(href)
            docket_match = re.search(r"\b(\d{4}-\d{3,5})\b", filename + " " + text)
            docket = docket_match.group(1) if docket_match else filename

            date_match = re.search(r"(\d{2})-(\d{2})-(\d{4})", filename)
            if date_match:
                month, day, year = date_match.groups()
                arg_date = datetime(int(year), int(month), int(day))
            else:
                arg_date = datetime.utcnow()

            title = text or docket

            cases.append({
                "docket": docket,
                "title": title,
                "date": arg_date,
                "mp3_url": mp3_url,
            })

    return cases

def load_existing_guids(feed_path: str) -> set[str]:
    tree = ET.parse(feed_path)
    root = tree.getroot()
    channel = root.find("channel")
    guids = set()
    for item in channel.findall("item"):
        guid_el = item.find("guid")
        if guid_el is not None and guid_el.text:
            guids.add(guid_el.text.strip())
    return guids

def download_mp3(mp3_url: str, out_path: str) -> int:
    resp = SESSION.get(mp3_url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return os.path.getsize(out_path)

def add_item_to_feed(feed_path: str, case: dict, local_filename: str, file_size: int):
    tree = ET.parse(feed_path)
    root = tree.getroot()
    channel = root.find("channel")

    item = ET.SubElement(channel, "item")

    title_el = ET.SubElement(item, "title")
    title_el.text = f"{case['docket']} – {case['title']}"

    enclosure_el = ET.SubElement(item, "enclosure")
    enclosure_el.set("url", f"{PODCAST_BASE_URL}/{local_filename}")
    enclosure_el.set("length", str(file_size))
    enclosure_el.set("type", "audio/mpeg")

    guid_el = ET.SubElement(item, "guid")
    guid_el.set("isPermaLink", "false")
    guid_el.text = case["docket"]

    pubdate_el = ET.SubElement(item, "pubDate")
    pubdate_el.text = format_datetime(case["date"])

    desc_el = ET.SubElement(item, "description")
    desc_el.text = f"Oral argument for docket {case['docket']}: {case['title']}."

    itunes_explicit_el = ET.SubElement(
        item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit"
    )
    itunes_explicit_el.text = "no"

    tree.write(feed_path, encoding="utf-8", xml_declaration=True)

def main():
    print("Discovering MP3 links from CAFed...")
    cases = discover_mp3_links()
    print(f"Found {len(cases)} audio links on site.")

    print("Loading existing GUIDs from feed.xml...")
    existing_guids = load_existing_guids(FEED_PATH)
    print(f"Existing GUIDs in feed: {len(existing_guids)}")

    new_cases = [c for c in cases if c["docket"] not in existing_guids]
    print(f"New cases to add: {len(new_cases)}")

    if not new_cases:
        print("No new cases. Exiting.")
        return

    for case in new_cases:
        docket = case["docket"]
        print(f"Processing new case {docket}...")

        local_filename = f"{docket}.mp3"
        if not os.path.exists(local_filename):
            size = download_mp3(case["mp3_url"], local_filename)
            print(f"Downloaded {local_filename} ({size} bytes).")
        else:
            size = os.path.getsize(local_filename)
            print(f"{local_filename} already exists, size {size} bytes.")

        add_item_to_feed(FEED_PATH, case, local_filename, size)
        print(f"Added {docket} to feed.xml")

    print("Done updating feed.")

if __name__ == "__main__":
    main()
