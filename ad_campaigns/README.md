# TechSelect Meta Ads Manager

A dedicated, safe, and policy-compliant Meta Ads management suite embedded directly inside **AffiliateTelegramBot**.

---

## 🔒 1. Local Security & Credentials Guarantee
All sensitive credentials (`META_ADS_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, `META_APP_ID`, `META_BUSINESS_ID`) are stored **strictly on your local machine**:
* In `c:\Users\conne\Downloads\AffiliateTelegramBot\.env` (blocked by `.gitignore`)
* In `~/.config/meta-ads-open-cli/credentials.json` (user home directory, not in any repo)
* In Windows User Environment Variables

**No tokens or API secrets will ever be committed or pushed to GitHub.**

---

## 💰 2. Understanding the ₹40 Budget & Meta's Minimum Limit
* **Meta's Global Policy:** Meta enforces a hard minimum daily budget equivalent to **$1 USD per day** (~**₹96.73 / day** in India).
* Attempting to set an automated daily budget lower than ₹96.73 triggers Meta API error `1885272: "Your ad set budget must be more than ₹96.73"`.
* **How to spend ₹40:**
  1. All campaigns are deployed in **`PAUSED`** status by default (**₹0 spend**).
  2. When you want to run a ₹40 test, unpause the ad set, let it run for **10 hours** (at ₹97/day pace, 10 hours costs exactly ~**₹40**), then pause it:
     ```powershell
     python ad_campaigns/techselect_ads.py pause <campaign_id>
     ```

---

## 🚀 3. High-Converting Optimized Ad Presets

Located in `ad_campaigns/ad_presets.json`:

1. **Telegram Deals Channel (`telegram_deals_growth`)**:
   * Target: `https://t.me/TechSelectDeals`
   * Hook: *"Tired of missing lightning deals? Real-time Amazon price drops with effective bank card pricing."*
2. **Website Traffic (`website_reviews_traffic`)**:
   * Target: `https://techselect.blog/`
   * Hook: *"Before spending ₹50,000+ on a laptop or phone, read our lab-tested benchmarks. Zero sponsored bias."*
3. **WhatsApp Community (`whatsapp_community_growth`)**:
   * Target: `https://whatsapp.com/channel/TechSelectDeals`
   * Hook: *"Get the top 3 best tech deals delivered straight to WhatsApp every morning."*
4. **Multi-Channel Hub (`multi_channel_hub`)**:
   * Cross-promotes the entire TechSelect ecosystem.

---

## 🛠️ 4. Quick Commands

```powershell
# List all active/paused campaigns
python ad_campaigns/techselect_ads.py list

# List all ad sets & current budgets
python ad_campaigns/techselect_ads.py adsets

# View all available creative presets
python ad_campaigns/techselect_ads.py presets

# Deploy a preset (safely creates campaign & ad set in PAUSED state)
python ad_campaigns/techselect_ads.py deploy telegram_deals_growth
python ad_campaigns/techselect_ads.py deploy website_reviews_traffic

# Immediately pause any campaign
python ad_campaigns/techselect_ads.py pause <campaign_id>
```
