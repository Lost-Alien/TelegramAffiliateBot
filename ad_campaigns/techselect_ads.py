#!/usr/bin/env python3
"""
TechSelect Meta Ads Campaign Manager
Allows creating, monitoring, and controlling Meta Ads for TechSelect
strictly adhering to safety defaults (PAUSED by default) and reading local credentials.
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv

# Base paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
PRESETS_FILE = Path(__file__).resolve().parent / "ad_presets.json"
CREDENTIALS_FILE = Path.home() / ".config" / "meta-ads-open-cli" / "credentials.json"

# Load environment
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

# Resolve credentials strictly locally
TOKEN = os.getenv("META_ADS_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID", "1411531287802586")
BUSINESS_ID = os.getenv("META_BUSINESS_ID", "4628675240696704")

if not TOKEN and CREDENTIALS_FILE.exists():
    try:
        creds = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        TOKEN = creds.get("access_token")
        ACCOUNT_ID = creds.get("account_id", ACCOUNT_ID)
    except Exception:
        pass

if not ACCOUNT_ID.startswith("act_"):
    ACT_ACCOUNT_ID = f"act_{ACCOUNT_ID}"
else:
    ACT_ACCOUNT_ID = ACCOUNT_ID
    ACCOUNT_ID = ACCOUNT_ID.replace("act_", "")

API_VERSION = "v22.0"
GRAPH_URL = f"https://graph.facebook.com/{API_VERSION}"

def api_call(endpoint: str, params: dict = None, data: dict = None, method: str = "GET") -> dict:
    """Execute a secure HTTP request to Meta Graph API."""
    if not TOKEN:
        print("[ERROR] META_ADS_ACCESS_TOKEN not found in local .env or credentials.json")
        sys.exit(1)

    url = f"{GRAPH_URL}/{endpoint}"
    query = {"access_token": TOKEN}
    if params:
        query.update(params)

    full_url = f"{url}?{urllib.parse.urlencode(query)}"

    encoded_data = None
    if data:
        data["access_token"] = TOKEN
        encoded_data = urllib.parse.urlencode(data).encode("utf-8")

    req = urllib.request.Request(full_url, data=encoded_data, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        try:
            parsed = json.loads(error_msg)
            err = parsed.get("error", {})
            print(f"[API ERROR {e.code}]: {err.get('error_user_title') or err.get('message')}")
            print(f"Details: {err.get('error_user_msg') or err.get('message')}")
        except Exception:
            print(f"[HTTP ERROR {e.code}]: {error_msg}")
        return None
    except Exception as e:
        print(f"[SYSTEM ERROR]: {e}")
        return None

def list_campaigns():
    """List all campaigns for TechSelect Ad Account."""
    print(f"\n[TechSelect Ads] Fetching campaigns for {ACT_ACCOUNT_ID}...\n")
    fields = "id,name,objective,status,effective_status,daily_budget,lifetime_budget,created_time"
    res = api_call(f"{ACT_ACCOUNT_ID}/campaigns", params={"fields": fields})
    if not res or "data" not in res:
        return
    data = res["data"]
    if not data:
        print("No campaigns found.")
        return
    for c in data:
        print(f"• ID: {c.get('id')}")
        print(f"  Name: {c.get('name')}")
        print(f"  Status: {c.get('status')} (Effective: {c.get('effective_status')})")
        print(f"  Objective: {c.get('objective')}")
        print(f"  Created: {c.get('created_time')}")
        print("-" * 50)

def list_adsets():
    """List all ad sets for TechSelect Ad Account."""
    print(f"\n[TechSelect Ads] Fetching ad sets for {ACT_ACCOUNT_ID}...\n")
    fields = "id,name,campaign_id,status,effective_status,daily_budget,bid_strategy,optimization_goal"
    res = api_call(f"{ACT_ACCOUNT_ID}/adsets", params={"fields": fields})
    if not res or "data" not in res:
        return
    data = res["data"]
    if not data:
        print("No ad sets found.")
        return
    for s in data:
        daily_inr = int(s.get("daily_budget", 0)) / 100
        print(f"• ID: {s.get('id')}")
        print(f"  Name: {s.get('name')}")
        print(f"  Daily Budget: ₹{daily_inr:.2f}")
        print(f"  Status: {s.get('status')}")
        print(f"  Goal: {s.get('optimization_goal')}")
        print("-" * 50)

def create_preset_campaign(preset_id: str):
    """Deploy a preset campaign (always created PAUSED for safety)."""
    if not PRESETS_FILE.exists():
        print(f"[ERROR] Presets file not found: {PRESETS_FILE}")
        return

    presets_data = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
    campaigns = {c["id"]: c for c in presets_data.get("ad_campaigns", [])}

    if preset_id not in campaigns:
        print(f"[ERROR] Unknown preset: {preset_id}")
        print(f"Available presets: {', '.join(campaigns.keys())}")
        return

    c = campaigns[preset_id]
    print(f"\nCreating Campaign from Preset: {c['campaign_name']}...")

    # Step 1: Create Campaign (PAUSED)
    campaign_res = api_call(
        f"{ACT_ACCOUNT_ID}/campaigns",
        data={
            "name": c["campaign_name"],
            "objective": c["objective"],
            "status": "PAUSED",
            "special_ad_categories": json.dumps([]),
            "is_adset_budget_sharing_enabled": "false"
        },
        method="POST"
    )

    if not campaign_res or "id" not in campaign_res:
        print("[FAIL] Failed to create campaign.")
        return

    campaign_id = campaign_res["id"]
    print(f"[SUCCESS] Created Campaign ID: {campaign_id} (Status: PAUSED)")

    # Step 2: Create Ad Set (PAUSED, min budget ₹97.00 = 9700 paise)
    print(f"Creating Ad Set: {c['ad_set_name']}...")
    adset_res = api_call(
        f"{ACT_ACCOUNT_ID}/adsets",
        data={
            "name": c["ad_set_name"],
            "campaign_id": campaign_id,
            "daily_budget": "9700",  # Minimum Meta daily budget in INR (~₹97)
            "billing_event": "IMPRESSIONS",
            "optimization_goal": "LINK_CLICKS",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "targeting": json.dumps({
                "geo_locations": c["targeting"]["geo_locations"],
                "age_min": c["targeting"]["age_min"],
                "age_max": c["targeting"]["age_max"],
                "targeting_automation": {"advantage_audience": 0}
            }),
            "status": "PAUSED"
        },
        method="POST"
    )

    if adset_res and "id" in adset_res:
        print(f"[SUCCESS] Created Ad Set ID: {adset_res['id']} (Status: PAUSED)")
        print("\nAll assets created safely in PAUSED status.")
        print(f"Destination URL: {c['destination_url']}")
        print(f"Ad Copy Headline: {c['creative']['headline']}")
    else:
        print("[WARN] Campaign was created, but Ad Set creation encountered an issue.")

def pause_campaign(campaign_id: str):
    """Pause a campaign immediately to prevent any spend."""
    print(f"Pausing campaign {campaign_id}...")
    res = api_call(f"{campaign_id}", data={"status": "PAUSED"}, method="POST")
    if res and res.get("success"):
        print(f"[SUCCESS] Campaign {campaign_id} is PAUSED.")
    else:
        print("[FAIL] Could not pause campaign.")

def main():
    if len(sys.argv) < 2:
        print("""
TechSelect Ads Manager (Meta Marketing API)
Account: act_1411531287802586 (Tech Select)

Commands:
  python techselect_ads.py list             List all campaigns
  python techselect_ads.py adsets           List all ad sets
  python techselect_ads.py presets          Show available optimized ad presets
  python techselect_ads.py deploy <preset>  Deploy preset (telegram_deals_growth, website_reviews_traffic, etc.)
  python techselect_ads.py pause <id>       Immediately pause a campaign
""")
        return

    cmd = sys.argv[1].lower()
    if cmd == "list":
        list_campaigns()
    elif cmd == "adsets":
        list_adsets()
    elif cmd == "presets":
        if PRESETS_FILE.exists():
            presets = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
            print("\nAvailable Optimized Presets for TechSelect:\n")
            for p in presets.get("ad_campaigns", []):
                print(f"• ID: {p['id']}")
                print(f"  Target: {p['target_platform']} ({p['destination_url']})")
                print(f"  Headline: {p['creative']['headline']}")
                print("-" * 50)
    elif cmd == "deploy" and len(sys.argv) >= 3:
        create_preset_campaign(sys.argv[2])
    elif cmd == "pause" and len(sys.argv) >= 3:
        pause_campaign(sys.argv[3])
    else:
        print("Unknown command. Run with no arguments for help.")

if __name__ == "__main__":
    main()
