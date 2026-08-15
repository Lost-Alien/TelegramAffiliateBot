"""
puzzle_poster.py — Auto-poster for SmartBrain Puzzles to X (Twitter).

Features:
  - Uploads puzzle images to Twitter via session-cookie Media Upload endpoint (free, no API quota).
  - Posts engaging puzzle challenge tweets with attached media.
  - Posts solution as a threaded reply under the question tweet.
  - Automatically deletes local image files on the AWS server after posting to save disk space.
  - Routine cleanup function to purge all cached media of posted puzzles.
  - CLI commands for manual posting, scraping, dry-runs, status reports, and continuous timers.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load local environment
load_dotenv()

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

# XActions Constants
_XACTIONS_BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
_XACTIONS_CREATE_TWEET_QUERY_ID = "SiM_cAu83R0wnrpmKQQSEw"

_XACTIONS_DEFAULT_FEATURES = {
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}


# ============================================================================
# Credentials & Session
# ============================================================================

def get_twitter_cookies() -> tuple[str, str]:
    """Retrieve auth_token and ct0 from environment or fallback configs."""
    auth_token = (
        os.getenv("TWITTER_AUTH_TOKEN", "").strip()
        or os.getenv("X_AUTH_TOKEN", "").strip()
    )
    ct0 = (
        os.getenv("TWITTER_CT0", "").strip()
        or os.getenv("X_CT0", "").strip()
    )

    # Try importing from config.py if present
    if not (auth_token and ct0):
        try:
            import config  # type: ignore
            auth_token = auth_token or getattr(config, "TWITTER_AUTH_TOKEN", "") or getattr(config, "X_AUTH_TOKEN", "")
            ct0 = ct0 or getattr(config, "TWITTER_CT0", "") or getattr(config, "X_CT0", "")
        except Exception:
            pass

    return auth_token, ct0


# ============================================================================
# Twitter Media Upload Engine
# ============================================================================

def upload_image_to_twitter(image_path: Path | str, auth_token: str, ct0: str) -> str | None:
    """Upload an image file to Twitter via upload.twitter.com/1.1/media/upload.json.

    Returns media_id_string on success, None on error.
    """
    path = Path(image_path)
    if not path.exists():
        logger.error(f"Image not found on disk: {path}")
        return None

    try:
        with open(path, "rb") as f:
            img_data = f.read()

        b64_img = base64.b64encode(img_data).decode("utf-8")
        post_data = urllib.parse.urlencode({"media_data": b64_img}).encode("utf-8")

        upload_url = "https://upload.twitter.com/1.1/media/upload.json"
        headers = {
            "Authorization": f"Bearer {urllib.parse.unquote(_XACTIONS_BEARER_TOKEN)}",
            "x-csrf-token": ct0,
            "x-twitter-auth-type": "OAuth2Session",
            "Cookie": f"auth_token={auth_token}; ct0={ct0};",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Origin": "https://x.com",
            "Referer": "https://x.com/compose/tweet",
        }

        req = urllib.request.Request(upload_url, data=post_data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        media_id = str(data.get("media_id_string") or data.get("media_id") or "")
        if media_id:
            logger.info(f"Uploaded image {path.name} -> Twitter Media ID: {media_id}")
            return media_id
        else:
            logger.error(f"Media upload returned unexpected payload: {data}")
            return None

    except Exception as e:
        logger.error(f"Failed to upload media {path.name} to Twitter: {e}")
        return None


# ============================================================================
# Tweet Creation Engine (GraphQL)
# ============================================================================

def post_tweet_graphql(
    text: str,
    auth_token: str,
    ct0: str,
    media_ids: list[str] | None = None,
    in_reply_to_tweet_id: str | None = None,
) -> tuple[bool, str]:
    """Create a tweet or thread reply using X's internal GraphQL endpoint."""
    query_id = _XACTIONS_CREATE_TWEET_QUERY_ID
    url = f"https://x.com/i/api/graphql/{query_id}/CreateTweet"

    headers = {
        "Authorization": f"Bearer {urllib.parse.unquote(_XACTIONS_BEARER_TOKEN)}",
        "x-csrf-token": ct0,
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-active-user": "yes",
        "x-twitter-client-language": "en",
        "Cookie": f"auth_token={auth_token}; ct0={ct0};",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Origin": "https://x.com",
        "Referer": "https://x.com/compose/tweet",
    }

    media_entities = [{"media_id": mid, "tagged_users": []} for mid in (media_ids or [])]

    variables: dict[str, Any] = {
        "tweet_text": text,
        "dark_request": False,
        "media": {
            "media_entities": media_entities,
            "possibly_sensitive": False,
        },
        "semantic_annotation_ids": [],
    }

    if in_reply_to_tweet_id:
        variables["reply"] = {
            "in_reply_to_tweet_id": in_reply_to_tweet_id,
            "exclude_reply_user_ids": [],
        }

    payload = {
        "variables": variables,
        "features": _XACTIONS_DEFAULT_FEATURES,
        "queryId": query_id,
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))

        tweet_result = (
            resp_data.get("data", {}).get("create_tweet", {}).get("tweet_results", {}).get("result")
            or resp_data.get("data", {}).get("create_tweet", {}).get("tweet_result", {}).get("result")
            or resp_data.get("data", {}).get("create_tweet")
        )

        if tweet_result:
            tweet_id = str(
                tweet_result.get("rest_id")
                or tweet_result.get("legacy", {}).get("id_str")
                or "OK"
            )
            return True, tweet_id

        errors = resp_data.get("errors", [])
        if errors:
            return False, errors[0].get("message", "Unknown GraphQL error")

        return True, "posted"

    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        return False, f"HTTP {e.code}: {e.reason} — {error_body}"
    except Exception as e:
        return False, f"Error posting tweet: {e}"


# ============================================================================
# Emoji Stripper & Text Utilities
# ============================================================================

def strip_emojis(text: str) -> str:
    """Remove all emojis and unicode pictographs from text."""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002700-\U000027BF"  # dingbats
        "\U00002600-\U000026FF"  # misc symbols
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FAFF"  # symbols
        "]+",
        flags=re.UNICODE,
    )
    clean = emoji_pattern.sub("", text)
    lines = [re.sub(r" +", " ", l).strip() for l in clean.split("\n")]
    return "\n".join(lines).strip()


# ============================================================================
# Image Watermark Engine (TechSelect Logo on Bottom-Right Corner)
# ============================================================================

def get_logo_path() -> Path | None:
    """Locate TechSelect logo file."""
    candidates = [
        BASE_DIR / "logo.png",
        BASE_DIR.parent / "logo.png",
        Path("/app/logo.png"),
    ]
    for p in candidates:
        if p.exists() and p.stat().st_size > 100:
            return p
    return None


def apply_techselect_watermark(image_path: Path | str, output_path: Path | str | None = None) -> Path:
    """Overlay TechSelect logo at the bottom-right corner of puzzle image.

    Returns the path to the watermarked image (or original image if logo is missing or PIL unavailable).
    """
    in_path = Path(image_path)
    logo_path = get_logo_path()

    if not logo_path or not in_path.exists():
        return in_path

    try:
        from PIL import Image, ImageDraw

        out_file = Path(output_path) if output_path else in_path.parent / f"wm_{in_path.name}"

        base_img = Image.open(in_path).convert("RGBA")
        logo_img = Image.open(logo_path).convert("RGBA")

        bw, bh = base_img.size
        # Target logo width: ~14% of base image width (min 70px, max 160px)
        logo_w = max(70, min(160, int(bw * 0.14)))
        logo_h = int(logo_w * (logo_img.size[1] / logo_img.size[0]))

        logo_resized = logo_img.resize((logo_w, logo_h), Image.Resampling.LANCZOS)

        # Rounded corner mask for clean appearance
        mask = Image.new("L", (logo_w, logo_h), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([(0, 0), (logo_w, logo_h)], radius=int(logo_w * 0.15), fill=255)

        # Position at bottom-right corner with responsive margin
        margin = max(15, int(bw * 0.025))
        pos_x = bw - logo_w - margin
        pos_y = bh - logo_h - margin

        base_img.paste(logo_resized, (pos_x, pos_y), mask)

        final_rgb = base_img.convert("RGB")
        final_rgb.save(out_file, "JPEG", quality=95)
        logger.info(f"✨ Applied TechSelect logo watermark at bottom-right -> {out_file.name}")
        return out_file

    except Exception as e:
        logger.warning(f"Watermarking skipped due to error: {e}")
        return in_path


# ============================================================================
# Formatting Templates (Strictly No Emojis)
# ============================================================================

def format_puzzle_tweet(puzzle: dict[str, Any]) -> str:
    """Format the primary puzzle tweet strictly without emojis and under 280 chars."""
    category = puzzle.get("category", "Brain Puzzle").split(",")[0].strip()
    raw_question = puzzle.get("question", "").strip()

    header = "BRAIN TEASER CHALLENGE"
    sub_header = f"[{category}]"
    cta = "Can you solve this? Look at the image and drop your answer in the comments.\nSolution is revealed in the thread below."
    hashtags = "#BrainTeaser #Puzzle #MathPuzzle #IQTest #SmartBrain #TechSelect"

    # Overhead calculation
    fixed_overhead = len(header) + len(sub_header) + len(cta) + len(hashtags) + 10
    allowed_q_len = max(30, 260 - fixed_overhead)

    question = raw_question
    if question and len(question) > allowed_q_len:
        question = question[: allowed_q_len - 3].rsplit(" ", 1)[0] + "..."

    lines = [
        header,
        sub_header,
        "",
    ]
    if question:
        lines.append(question)
        lines.append("")

    lines.extend([
        cta,
        "",
        hashtags,
    ])

    tweet = "\n".join(lines).strip()
    return strip_emojis(tweet)


def format_solution_reply(puzzle: dict[str, Any]) -> str:
    """Format the solution reply tweet strictly without emojis and under 260 chars."""
    raw_answer = puzzle.get("answer", "").strip()
    if not raw_answer or raw_answer.upper() == "N/A":
        return ""

    header = "PUZZLE SOLUTION & REASONING:"
    footer = "Did you get it right? Follow @techselect_blog for daily puzzles!"
    fixed_overhead = len(header) + len(footer) + len("Answer: ") + 8
    max_ans_len = max(40, 260 - fixed_overhead)

    answer = raw_answer
    if len(answer) > max_ans_len:
        answer = answer[: max_ans_len - 3].rsplit(" ", 1)[0] + "..."

    lines = [
        header,
        "",
        f"Answer: {answer}",
        "",
        footer,
    ]
    reply = "\n".join(lines).strip()
    return strip_emojis(reply)


# ============================================================================
# AWS Image Cleanup Engine
# ============================================================================

def delete_local_image(puzzle: dict[str, Any]) -> bool:
    """Delete local image file from AWS server disk to reclaim space."""
    local_rel = puzzle.get("local_image", "")
    if not local_rel:
        return False

    file_path = BASE_DIR / local_rel
    if file_path.exists():
        try:
            file_path.unlink()
            logger.info(f"🗑️ Cleaned up image file from AWS server: {file_path.name}")
            return True
        except Exception as e:
            logger.warning(f"Could not delete {file_path}: {e}")
            return False
    return False


def cleanup_posted_images(purge_all: bool = False) -> int:
    """Routine check: purge cached image files for posted puzzles (or all cached images if purge_all=True)."""
    from puzzle_scraper import load_puzzles_dataset

    puzzles = load_puzzles_dataset()
    deleted_count = 0
    reclaimed_bytes = 0

    posted_ids = {p["id"] for p in puzzles if p.get("posted")}

    if IMAGES_DIR.exists():
        for file in IMAGES_DIR.iterdir():
            if file.is_file():
                file_stem = file.stem
                if purge_all or file_stem in posted_ids or file.stat().st_size == 0 or file.name.startswith("wm_"):
                    try:
                        sz = file.stat().st_size
                        file.unlink()
                        deleted_count += 1
                        reclaimed_bytes += sz
                    except Exception as e:
                        logger.warning(f"Failed to delete {file.name}: {e}")

    logger.info(
        f"🧹 Routine Cleanup complete: Deleted {deleted_count} cached images ({reclaimed_bytes / 1024:.1f} KB reclaimed)."
    )
    return deleted_count


# ============================================================================
# Posting Workflow
# ============================================================================

def post_puzzle(
    puzzle: dict[str, Any],
    dry_run: bool = False,
    post_solution: bool = True,
    clean_image_after: bool = True,
) -> bool:
    """Post a single puzzle with attached image and optional solution reply."""
    from puzzle_scraper import download_puzzle_image, load_puzzles_dataset, save_puzzles_dataset

    pid = puzzle["id"]
    auth_token, ct0 = get_twitter_cookies()

    if not (auth_token and ct0):
        logger.error("❌ Twitter session cookies (TWITTER_AUTH_TOKEN, TWITTER_CT0) not configured!")
        return False

    # Check local image or download on-demand
    local_rel = puzzle.get("local_image", f"data/puzzle_images/{pid}.jpg")
    local_path = BASE_DIR / local_rel
    downloaded_fresh = False

    if not local_path.exists():
        img_url = puzzle.get("image_url", "")
        if img_url:
            logger.info(f"Image not on disk for {pid}, downloading from {img_url}...")
            downloaded_fresh = download_puzzle_image(img_url, local_path)

    if not local_path.exists():
        logger.error(f"Cannot post {pid}: Image file missing and download failed.")
        return False

    tweet_text = format_puzzle_tweet(puzzle)
    reply_text = format_solution_reply(puzzle) if post_solution else ""

    logger.info(f"--- Preparing Tweet for [{pid}] ---")
    logger.info(f"Main Tweet:\n{tweet_text}\n")
    if reply_text:
        logger.info(f"Reply Tweet:\n{reply_text}\n")

    # 1. Apply TechSelect Logo Watermark on Bottom-Right Corner
    upload_target = apply_techselect_watermark(local_path)
    is_temp_wm = upload_target != local_path

    if dry_run:
        logger.info(f"🧪 [DRY-RUN] Would upload {upload_target.name} (with TechSelect watermark) and post to X. Skipping actual post.")
        if is_temp_wm and upload_target.exists():
            upload_target.unlink()
        if downloaded_fresh and clean_image_after and local_path.exists():
            local_path.unlink()
        return True

    # 2. Upload Media to Twitter
    media_id = upload_image_to_twitter(upload_target, auth_token, ct0)

    # Clean up temporary watermarked image immediately after upload
    if is_temp_wm and upload_target.exists():
        try:
            upload_target.unlink()
        except Exception:
            pass

    if not media_id:
        logger.error(f"❌ Failed to upload image for {pid}. Aborting post.")
        return False

    # 3. Post Main Tweet with Image (Strictly No Emojis)
    ok, main_tweet_id = post_tweet_graphql(
        text=tweet_text,
        auth_token=auth_token,
        ct0=ct0,
        media_ids=[media_id],
    )

    if not ok:
        logger.error(f"❌ Failed to post main tweet for {pid}: {main_tweet_id}")
        return False

    logger.info(f"✅ Main Tweet posted successfully! Tweet ID: {main_tweet_id}")

    # 4. Post Solution Reply (if available, strictly no emojis)
    reply_tweet_id = None
    if reply_text and main_tweet_id and main_tweet_id != "OK":
        time.sleep(2)  # brief pause before thread reply
        rok, r_id = post_tweet_graphql(
            text=reply_text,
            auth_token=auth_token,
            ct0=ct0,
            in_reply_to_tweet_id=main_tweet_id,
        )
        if rok:
            reply_tweet_id = r_id
            logger.info(f"✅ Solution reply posted in thread! Tweet ID: {reply_tweet_id}")
        else:
            logger.warning(f"⚠️ Solution reply failed: {r_id}")

    # 5. Update Dataset Record
    all_puzzles = load_puzzles_dataset()
    now_iso = datetime.now(timezone.utc).isoformat()
    for p in all_puzzles:
        if p["id"] == pid:
            p["posted"] = True
            p["posted_at"] = now_iso
            p["tweet_id"] = main_tweet_id
            p["reply_tweet_id"] = reply_tweet_id

    save_puzzles_dataset(all_puzzles)

    # 6. AWS Disk Cleanup (Remove source image after successful post)
    if clean_image_after:
        delete_local_image(puzzle)

    return True


def post_next_puzzle(dry_run: bool = False) -> bool:
    """Find and post the next unposted puzzle."""
    from puzzle_scraper import load_puzzles_dataset

    puzzles = load_puzzles_dataset()
    unposted = [p for p in puzzles if not p.get("posted")]

    if not unposted:
        logger.info("🎉 All puzzles have already been posted! Run scraper to find new ones.")
        return False

    target = unposted[0]
    logger.info(f"Next puzzle to post: [{target['id']}] {target.get('category')} (Remaining unposted: {len(unposted)})")
    return post_puzzle(target, dry_run=dry_run)


def print_status() -> None:
    """Print a summary table of puzzles dataset and disk usage."""
    from puzzle_scraper import load_puzzles_dataset

    puzzles = load_puzzles_dataset()
    total = len(puzzles)
    posted = sum(1 for p in puzzles if p.get("posted"))
    unposted = total - posted

    cached_images = 0
    disk_bytes = 0
    if IMAGES_DIR.exists():
        for f in IMAGES_DIR.iterdir():
            if f.is_file():
                cached_images += 1
                disk_bytes += f.stat().st_size

    print("\n==================================================")
    print(" 🧩 SMARTBRAIN PUZZLES AUTO-POSTER STATUS")
    print("==================================================")
    print(f" Total Puzzles in DB : {total}")
    print(f" Already Posted      : {posted}")
    print(f" Pending to Post     : {unposted}")
    print(f" Cached Local Images : {cached_images} ({disk_bytes / 1024:.1f} KB on AWS disk)")
    print("==================================================")

    if unposted > 0:
        print("\nNext 3 Puzzles in Queue:")
        pending = [p for p in puzzles if not p.get("posted")][:3]
        for i, p in enumerate(pending, 1):
            q_short = p.get("question", "")[:60] + "..." if len(p.get("question", "")) > 60 else p.get("question", "")
            print(f" {i}. [{p['id']}] {p.get('category')}: {q_short}")
    print()


# ============================================================================
# CLI Entrypoint
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="SmartBrain Puzzles Twitter Auto-Poster")
    parser.add_argument("--scrape", action="store_true", help="Scrape latest puzzles from smartbrainpuzzles.com")
    parser.add_argument("--status", action="store_true", help="Show status and statistics")
    parser.add_argument("--post-one", action="store_true", help="Post next unposted puzzle")
    parser.add_argument("--post-id", type=str, help="Post specific puzzle by ID")
    parser.add_argument("--cleanup", action="store_true", help="Run routine check and purge posted images from AWS server")
    parser.add_argument("--purge-all", action="store_true", help="Purge all cached images regardless of status")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without publishing tweet")
    parser.add_argument("--auto", action="store_true", help="Run automatic scheduler loop")
    parser.add_argument("--interval", type=int, default=3600, help="Interval in seconds for auto scheduler (default 3600s)")

    args = parser.parse_args()

    if args.scrape:
        from puzzle_scraper import scrape_all_puzzles
        scrape_all_puzzles(download_images=True)
        return

    if args.cleanup or args.purge_all:
        cleanup_posted_images(purge_all=args.purge_all)
        return

    if args.status:
        print_status()
        return

    if args.post_id:
        from puzzle_scraper import load_puzzles_dataset
        puzzles = load_puzzles_dataset()
        target = next((p for p in puzzles if p["id"] == args.post_id), None)
        if not target:
            logger.error(f"Puzzle ID '{args.post_id}' not found in database!")
            sys.exit(1)
        post_puzzle(target, dry_run=args.dry_run)
        return

    if args.post_one:
        post_next_puzzle(dry_run=args.dry_run)
        return

    if args.auto:
        logger.info(f"🚀 Starting Auto-Poster Scheduler (Posting 1 puzzle every {args.interval}s)...")
        while True:
            post_next_puzzle(dry_run=args.dry_run)
            cleanup_posted_images()
            logger.info(f"Sleeping for {args.interval}s until next puzzle...")
            time.sleep(args.interval)

    # If no flags passed, display status
    print_status()


if __name__ == "__main__":
    main()
