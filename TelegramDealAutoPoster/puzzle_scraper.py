"""
puzzle_scraper.py — Scraper and image downloader for SmartBrain Puzzles.

Extracts all puzzles from https://www.smartbrainpuzzles.com/puzzles/ and subcategories:
  - ID, Category, Question prompt, Solution/Explanation, Image URL, Source URL
  - Downloads high-resolution images to `data/puzzle_images/`
  - Persists structured dataset in `data/puzzles.json` (preserves existing posted status)
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Base paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "puzzle_images"
PUZZLES_JSON = DATA_DIR / "puzzles.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

CATEGORIES = [
    "https://www.smartbrainpuzzles.com/puzzles/",
    "https://www.smartbrainpuzzles.com/puzzles/hard-puzzles/",
    "https://www.smartbrainpuzzles.com/puzzles/iq-questions/",
    "https://www.smartbrainpuzzles.com/puzzles/logic-puzzles/",
    "https://www.smartbrainpuzzles.com/puzzles/math-puzzles/",
    "https://www.smartbrainpuzzles.com/puzzles/puzzle-games/",
    "https://www.smartbrainpuzzles.com/puzzles/rebus-puzzles/",
    "https://www.smartbrainpuzzles.com/puzzles/riddles/",
    "https://www.smartbrainpuzzles.com/puzzles/trivia-quiz/",
]


def _fetch_html(url: str, timeout: int = 20) -> str:
    """Fetch raw HTML for a URL."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def download_puzzle_image(image_url: str, dest_path: Path | str, timeout: int = 25) -> bool:
    """Download image to disk if not already downloaded."""
    target = Path(dest_path)
    if target.exists() and target.stat().st_size > 1000:
        return True

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(image_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if len(data) > 500:
            with open(target, "wb") as f:
                f.write(data)
            logger.info(f"Downloaded image ({len(data)} bytes) -> {target.name}")
            return True
        else:
            logger.warning(f"Downloaded image too small ({len(data)} bytes): {image_url}")
            return False
    except Exception as e:
        logger.error(f"Failed to download image {image_url}: {e}")
        return False


def _clean_text(text: str) -> str:
    """Clean whitespace and strip redundant prefixes."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned


def _clean_answer(raw_answer: str) -> str:
    """Strip 'Answer:' or 'Answer :' prefix from solution string."""
    cleaned = _clean_text(raw_answer)
    cleaned = re.sub(r"^(?:Answer\s*:?\s*)+", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def load_puzzles_dataset() -> list[dict[str, Any]]:
    """Load existing dataset from puzzles.json."""
    if PUZZLES_JSON.exists():
        try:
            with open(PUZZLES_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {PUZZLES_JSON}: {e}")
    return []


def save_puzzles_dataset(puzzles: list[dict[str, Any]]) -> None:
    """Save dataset to puzzles.json."""
    PUZZLES_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(PUZZLES_JSON, "w", encoding="utf-8") as f:
        json.dump(puzzles, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(puzzles)} puzzles to {PUZZLES_JSON}")


def scrape_all_puzzles(download_images: bool = True) -> list[dict[str, Any]]:
    """Scrape puzzles from all categories, merge with existing state, and download images."""
    existing_puzzles = {p["id"]: p for p in load_puzzles_dataset() if "id" in p}
    scraped_map: dict[str, dict[str, Any]] = {}

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Starting scrape across %d category URLs...", len(CATEGORIES))

    for cat_url in CATEGORIES:
        try:
            html = _fetch_html(cat_url)
            soup = BeautifulSoup(html, "html.parser")
            boxes = soup.find_all("div", class_="puzzles-box")
            logger.info(f"Found {len(boxes)} boxes on {cat_url}")

            for box in boxes:
                body = box.find("div", class_="puzzles-body")
                if not body:
                    continue

                # ID extraction
                likebtn = body.find("span", class_="likebtn-wrapper")
                pid = likebtn.get("data-identifier") if likebtn else None
                if not pid:
                    ans_el = body.find("h4", class_="puzzles-anw")
                    pid = ans_el.get("id") if ans_el else None
                if not pid:
                    url_attr = likebtn.get("data-item_url") if likebtn else ""
                    if url_attr:
                        pid = url_attr.rstrip("/").split("/")[-1]
                    else:
                        continue

                pid = str(pid).strip()

                # Category
                header = box.find("div", class_="puzzles-header")
                category = _clean_text(header.find("h2").get_text()) if header and header.find("h2") else "Brain Puzzles"

                # Question prompt
                q_el = body.find("h3")
                question = _clean_text(q_el.get_text()) if q_el else ""

                # Image URL
                img_el = body.find("img", class_="pzl-img")
                img_url = (
                    likebtn.get("data-item_image")
                    if likebtn and likebtn.get("data-item_image")
                    else (img_el["src"] if img_el and "src" in img_el.attrs else "")
                )

                # Answer
                ans_el = body.find("h4", class_="puzzles-anw")
                raw_ans = ans_el.get_text() if ans_el else ""
                answer = _clean_answer(raw_ans)

                # Source item URL
                item_url = likebtn.get("data-item_url") if likebtn else cat_url

                # Target image filename
                ext = ".jpg"
                if ".png" in img_url.lower():
                    ext = ".png"
                img_filename = f"{pid}{ext}"
                local_img_path = IMAGES_DIR / img_filename
                rel_img_path = f"data/puzzle_images/{img_filename}"

                # Download image if requested and not already downloaded
                if download_images and img_url:
                    download_puzzle_image(img_url, local_img_path)

                # Existing record to preserve status
                existing = existing_puzzles.get(pid, {})

                puzzle_record: dict[str, Any] = {
                    "id": pid,
                    "category": category,
                    "question": question,
                    "answer": answer if answer.upper() != "N/A" else existing.get("answer", "N/A"),
                    "image_url": img_url,
                    "local_image": rel_img_path if local_img_path.exists() else existing.get("local_image", ""),
                    "source_url": item_url,
                    "posted": existing.get("posted", False),
                    "posted_at": existing.get("posted_at", None),
                    "tweet_id": existing.get("tweet_id", None),
                    "reply_tweet_id": existing.get("reply_tweet_id", None),
                }

                scraped_map[pid] = puzzle_record

        except Exception as e:
            logger.error(f"Error scraping {cat_url}: {e}")

    final_list = list(scraped_map.values())
    for pid, old_record in existing_puzzles.items():
        if pid not in scraped_map:
            final_list.append(old_record)

    save_puzzles_dataset(final_list)

    total = len(final_list)
    with_local_img = sum(1 for p in final_list if (BASE_DIR / p.get("local_image", "")).exists())
    posted_cnt = sum(1 for p in final_list if p.get("posted"))
    logger.info(
        f"Scrape Complete! Total Puzzles: {total} | Downloaded Images: {with_local_img}/{total} | Posted: {posted_cnt}/{total}"
    )

    return final_list


if __name__ == "__main__":
    scrape_all_puzzles(download_images=True)
