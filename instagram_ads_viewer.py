#!/usr/bin/env python3
"""
Instagram Ads & Business Data Viewer

Parses Instagram data export (HTML format) and generates an interactive
local HTML dashboard visualizing your ad-related data.
"""

import html
import json
import sys
import webbrowser
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

# When bundled by PyInstaller, _MEIPASS points to the temp extraction dir
_BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))

def _load_chartjs():
    """Load Chart.js source -- bundled file first, CDN tag as fallback."""
    chartjs_path = _BUNDLE_DIR / "chartjs.min.js"
    if chartjs_path.exists():
        return f"<script>{chartjs_path.read_text(encoding='utf-8')}</script>"
    return '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>'


# -- HTML Parsers --

class TextExtractor(HTMLParser):
    """Extracts text content from divs with specific CSS classes."""
    def __init__(self, target_classes):
        super().__init__()
        self.target_classes = target_classes
        self.capturing = False
        self.current_text = ""
        self.texts = []
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if self.capturing:
            self.depth += 1
        for _, v in attrs:
            if v and any(c in v for c in self.target_classes):
                self.capturing = True
                self.depth = 1
                self.current_text = ""

    def handle_data(self, data):
        if self.capturing:
            self.current_text += data

    def handle_endtag(self, tag):
        if self.capturing:
            self.depth -= 1
            if self.depth <= 0:
                t = self.current_text.strip()
                if t:
                    self.texts.append(t)
                self.capturing = False
                self.current_text = ""


class FlatTextExtractor(HTMLParser):
    """Extracts text from innermost _a6-p divs, yielding each leaf text separately."""
    def __init__(self):
        super().__init__()
        self.in_target = False
        self.texts = []

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            classes = ""
            for k, v in attrs:
                if k == "class":
                    classes = v
            if "_a6-p" in classes:
                self.in_target = True

    def handle_data(self, data):
        d = data.strip()
        if self.in_target and d:
            self.texts.append(d)

    def handle_endtag(self, tag):
        if tag == "div":
            self.in_target = False


class LinkExtractor(HTMLParser):
    """Extracts business names from strong>a tags (off-meta activity index)."""
    def __init__(self):
        super().__init__()
        self.in_strong = False
        self.in_link = False
        self.names = []

    def handle_starttag(self, tag, attrs):
        if tag == "strong":
            self.in_strong = True
        if tag == "a" and self.in_strong:
            self.in_link = True

    def handle_data(self, data):
        if self.in_link:
            d = data.strip()
            if d:
                self.names.append(d)

    def handle_endtag(self, tag):
        if tag == "a":
            self.in_link = False
        if tag == "strong":
            self.in_strong = False


class TableExtractor(HTMLParser):
    """Extracts key-value pairs from table cells."""
    def __init__(self):
        super().__init__()
        self.in_label = False
        self.in_value = False
        self.current_label = ""
        self.current_value = ""
        self.pairs = []

    def handle_starttag(self, tag, attrs):
        if tag != "td":
            return
        classes = ""
        for k, v in attrs:
            if k == "class":
                classes = v
        if "_a6_q" in classes:
            self.in_label = True
            self.in_value = False
            self.current_label = ""
        elif "_a6_r" in classes:
            self.in_value = True
            self.in_label = False
            self.current_value = ""

    def handle_data(self, data):
        if self.in_label:
            self.current_label += data
        elif self.in_value:
            self.current_value += data

    def handle_endtag(self, tag):
        if tag == "td":
            if self.in_value:
                self.pairs.append((self.current_label.strip(), self.current_value.strip()))
                self.in_value = False
            elif self.in_label:
                self.in_label = False


# -- Data Parsers --

def parse_ad_preferences(filepath):
    if not filepath.exists():
        return []
    ext = FlatTextExtractor()
    ext.feed(filepath.read_text(encoding="utf-8"))
    texts = ext.texts
    entries = []
    i = 0
    while i < len(texts):
        t = texts[i]
        if t == "Event" and i + 1 < len(texts):
            entry = {"event": texts[i + 1]}
            i += 2
            if i < len(texts) and texts[i] == "Ad title" and i + 1 < len(texts):
                entry["ad_title"] = texts[i + 1]
                i += 2
            if i < len(texts) and texts[i] == "Creation time" and i + 1 < len(texts):
                entry["creation_time"] = texts[i + 1]
                i += 2
            entries.append(entry)
        else:
            i += 1
    return entries


def parse_ads_viewed(filepath):
    if not filepath.exists():
        return []
    ext = TextExtractor(["_a6-p", "_a6_q", "_a6_r"])
    ext.feed(filepath.read_text(encoding="utf-8"))
    texts = ext.texts
    advertisers = []
    current = {}
    for i, t in enumerate(texts):
        if t == "Name" and i + 1 < len(texts) and texts[i + 1] not in (
            "URL", "Username", "Ad library public URL", "Owner", "Name"
        ):
            if current.get("name"):
                advertisers.append(current)
            current = {"name": texts[i + 1]}
        elif t == "Username" and i + 1 < len(texts) and texts[i + 1] not in (
            "URL", "Name", "Ad library public URL", "Owner", "Username"
        ):
            current["username"] = texts[i + 1]
    if current.get("name"):
        advertisers.append(current)
    return advertisers


def parse_other_categories(filepath):
    if not filepath.exists():
        return []
    ext = FlatTextExtractor()
    ext.feed(filepath.read_text(encoding="utf-8"))
    return [t for t in ext.texts if t not in ("Name",)]


def parse_submitted_info(filepath):
    if not filepath.exists():
        return {}
    p = TableExtractor()
    p.feed(filepath.read_text(encoding="utf-8"))
    return dict(p.pairs)


def parse_subscription(filepath):
    if not filepath.exists():
        return {}
    p = TableExtractor()
    p.feed(filepath.read_text(encoding="utf-8"))
    return dict(p.pairs)


def parse_off_meta_index(filepath):
    if not filepath.exists():
        return []
    p = LinkExtractor()
    p.feed(filepath.read_text(encoding="utf-8"))
    return p.names


def parse_off_meta_detail(filepath):
    if not filepath.exists():
        return []
    ext = TextExtractor(["_a6-p", "_a6_q", "_a6_r"])
    ext.feed(filepath.read_text(encoding="utf-8"))
    texts = ext.texts
    events = []
    current = {}
    for i, t in enumerate(texts):
        if t == "Event" and i + 1 < len(texts):
            if current:
                events.append(current)
            current = {"event": texts[i + 1]}
        elif t == "Received on" and i + 1 < len(texts):
            current["date"] = texts[i + 1]
    if current:
        events.append(current)
    return events


def parse_posts_viewed(filepath):
    if not filepath.exists():
        return []
    ext = TextExtractor(["_a6-p", "_a6_q", "_a6_r"])
    ext.feed(filepath.read_text(encoding="utf-8"))
    texts = ext.texts
    accounts = []
    current = {}
    for i, t in enumerate(texts):
        if t == "Name" and i + 1 < len(texts) and texts[i + 1] not in (
            "URL", "Username", "Owner", "Name"
        ):
            if current.get("name"):
                accounts.append(current)
            current = {"name": texts[i + 1]}
        elif t == "Username" and i + 1 < len(texts) and texts[i + 1] not in (
            "URL", "Name", "Owner", "Username"
        ):
            current["username"] = texts[i + 1]
    if current.get("name"):
        accounts.append(current)
    return accounts


def parse_videos_watched(filepath):
    return parse_posts_viewed(filepath)


# -- Analysis Helpers --

def count_names(items, key="name"):
    counts = {}
    for item in items:
        name = item.get(key, "Unknown")
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def parse_date(date_str):
    for fmt in ("%b %d, %Y %I:%M %p", "%b %d, %Y %I:%M:%S %p", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def monthly_timeline(entries, date_key="creation_time"):
    months = {}
    for e in entries:
        d = parse_date(e.get(date_key, ""))
        if d:
            key = d.strftime("%Y-%m")
            months[key] = months.get(key, 0) + 1
    return dict(sorted(months.items()))


# -- HTML Report Generator --

def generate_report(data, output_path):
    """Generate a self-contained monochrome HTML report."""

    ad_prefs = data["ad_preferences"]
    ads_viewed = data["ads_viewed"]
    categories = data["categories"]
    submitted = data["submitted_info"]
    subscription = data["subscription"]
    off_meta_businesses = data["off_meta_businesses"]
    off_meta_events = data["off_meta_events"]
    posts_viewed = data["posts_viewed"]
    videos_watched = data["videos_watched"]

    top_advertisers = count_names(ads_viewed)
    top_20_advertisers = dict(list(top_advertisers.items())[:20])
    top_post_accounts = count_names(posts_viewed)
    top_20_posts = dict(list(top_post_accounts.items())[:20])
    top_video_accounts = count_names(videos_watched)
    top_20_videos = dict(list(top_video_accounts.items())[:20])
    hidden_ads_timeline = monthly_timeline(ad_prefs)

    hidden_event_types = {}
    for e in ad_prefs:
        hidden_event_types[e.get("event", "Unknown")] = hidden_event_types.get(e.get("event", "Unknown"), 0) + 1

    off_meta_event_types = {}
    for events in off_meta_events.values():
        for e in events:
            evt = e.get("event", "UNKNOWN")
            off_meta_event_types[evt] = off_meta_event_types.get(evt, 0) + 1
    off_meta_event_types = dict(sorted(off_meta_event_types.items(), key=lambda x: -x[1]))

    off_meta_by_biz = {k: len(v) for k, v in off_meta_events.items()}
    off_meta_by_biz = dict(sorted(off_meta_by_biz.items(), key=lambda x: -x[1]))

    all_off_meta = []
    for events in off_meta_events.values():
        for e in events:
            if "date" in e:
                all_off_meta.append({"creation_time": e["date"]})
    off_meta_timeline = monthly_timeline(all_off_meta)

    total_content = len(posts_viewed) + len(videos_watched) + len(ads_viewed)
    ads_pct = round(len(ads_viewed) / total_content * 100, 1) if total_content else 0
    top5_vals = list(top_advertisers.values())[:5]
    top5_pct = round(sum(top5_vals) / len(ads_viewed) * 100, 1) if ads_viewed else 0

    def js_json(obj):
        return json.dumps(obj, ensure_ascii=False)

    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>What Instagram Knows About You</title>
{_load_chartjs()}
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: 'SF Mono', 'Consolas', 'Monaco', 'Menlo', monospace;
    background: #ffffff;
    color: #000000;
    line-height: 1.8;
    -webkit-font-smoothing: antialiased;
    font-size: 14px;
  }}

  .container {{ max-width: 720px; margin: 0 auto; padding: 0 24px; }}

  .hero {{
    padding: 120px 24px 80px;
    border-bottom: 1px solid #000;
  }}
  .hero-content {{ max-width: 720px; margin: 0 auto; }}
  .hero-label {{
    font-size: 0.7em;
    letter-spacing: 0.25em;
    text-transform: uppercase;
    color: #999;
    margin-bottom: 32px;
  }}
  .hero h1 {{
    font-size: clamp(2em, 5vw, 3.2em);
    font-weight: 400;
    color: #000;
    line-height: 1.15;
    letter-spacing: -0.02em;
    margin-bottom: 24px;
  }}
  .hero h1 em {{ font-style: italic; }}
  .hero-sub {{
    font-size: 0.9em;
    color: #666;
    line-height: 1.8;
    max-width: 520px;
  }}
  .hero-stats {{
    display: flex;
    gap: 40px;
    margin-top: 48px;
    flex-wrap: wrap;
  }}
  .hero-stat {{
    border-left: 1px solid #000;
    padding-left: 16px;
  }}
  .hero-stat .n {{
    font-size: 2em;
    font-weight: 400;
    color: #000;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }}
  .hero-stat .l {{
    font-size: 0.65em;
    color: #999;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    margin-top: 6px;
  }}

  .section {{
    padding: 64px 0;
    border-bottom: 1px solid #e0e0e0;
  }}
  .section:last-child {{ border-bottom: none; }}
  .section-number {{
    font-size: 0.65em;
    letter-spacing: 0.25em;
    text-transform: uppercase;
    color: #999;
    margin-bottom: 12px;
  }}
  .section h2 {{
    font-size: clamp(1.3em, 3vw, 1.8em);
    font-weight: 400;
    letter-spacing: -0.01em;
    line-height: 1.3;
    margin-bottom: 10px;
    color: #000;
  }}
  .section-desc {{
    font-size: 0.85em;
    color: #666;
    max-width: 560px;
    margin-bottom: 36px;
    line-height: 1.8;
  }}

  .card {{
    border: 1px solid #e0e0e0;
    padding: 28px;
    margin-bottom: 16px;
  }}
  .card-label {{
    font-size: 0.6em;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: #999;
    margin-bottom: 20px;
  }}
  .chart-container {{ position: relative; height: 380px; width: 100%; }}
  .chart-container.tall {{ height: 500px; }}
  .chart-container.short {{ height: 260px; }}

  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }}
  @media (max-width: 768px) {{
    .grid-2, .grid-3 {{ grid-template-columns: 1fr; }}
  }}

  .dossier {{ border: 1px solid #000; padding: 32px; }}
  .dossier-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
  @media (max-width: 768px) {{ .dossier-grid {{ grid-template-columns: 1fr; }} }}
  .dossier-field {{ border-bottom: 1px solid #e0e0e0; padding: 10px 0; }}
  .dossier-field .label {{
    font-size: 0.6em;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: #999;
    margin-bottom: 4px;
  }}
  .dossier-field .value {{ font-size: 0.95em; color: #000; }}

  .tag-row {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }}
  .tag {{
    border: 1px solid #000;
    padding: 4px 10px;
    font-size: 0.7em;
    letter-spacing: 0.05em;
  }}

  .insight {{
    border-left: 2px solid #000;
    padding: 16px 20px;
    margin: 24px 0;
    font-size: 0.85em;
    line-height: 1.8;
    color: #333;
  }}

  .data-list {{ columns: 2; column-gap: 32px; }}
  .data-list-item {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 6px 0;
    border-bottom: 1px solid #f0f0f0;
    break-inside: avoid;
    font-size: 0.8em;
  }}
  .data-list-item .name {{ color: #000; }}
  .data-list-item .ct {{
    font-variant-numeric: tabular-nums;
    color: #000;
    min-width: 32px;
    text-align: right;
  }}
  @media (max-width: 768px) {{ .data-list {{ columns: 1; }} }}

  .inv {{ background: #000; color: #fff; padding: 64px 0; }}
  .inv .section {{ border-bottom-color: #222; }}
  .inv .section-number {{ color: #666; }}
  .inv h2 {{ color: #fff; }}
  .inv .section-desc {{ color: #888; }}
  .inv .card {{ border-color: #222; background: transparent; }}
  .inv .card-label {{ color: #555; }}
  .inv .insight {{ border-left-color: #fff; color: #aaa; }}
  .inv .data-list-item {{ border-bottom-color: #222; }}
  .inv .data-list-item .name, .inv .data-list-item .ct {{ color: #ccc; }}

  .footer {{
    text-align: center;
    padding: 40px 24px;
    font-size: 0.7em;
    color: #999;
    letter-spacing: 0.05em;
  }}

  .reveal {{
    opacity: 0;
    transform: translateY(20px);
    transition: opacity 0.6s ease, transform 0.6s ease;
  }}
  .reveal.visible {{ opacity: 1; transform: translateY(0); }}
</style>
</head>
<body>

<div class="hero">
  <div class="hero-content">
    <div class="hero-label">Instagram Surveillance Report</div>
    <h1>What Instagram <em>knows</em> about you</h1>
    <p class="hero-sub">
      This report reveals the advertising profile Instagram has built from your activity,
      the categories they've assigned you, and the companies tracking you beyond the app.
    </p>
    <div class="hero-stats">
      <div class="hero-stat"><div class="n">{len(ads_viewed)}</div><div class="l">Ads served</div></div>
      <div class="hero-stat"><div class="n">{len(top_advertisers)}</div><div class="l">Advertisers</div></div>
      <div class="hero-stat"><div class="n">{len(off_meta_businesses)}</div><div class="l">Off-app trackers</div></div>
      <div class="hero-stat"><div class="n">{total_content:,}</div><div class="l">Content logged</div></div>
    </div>
  </div>
</div>

<div class="container">

<div class="section reveal">
  <div class="section-number">01 -- Your profile</div>
  <h2>The identity Instagram built for you</h2>
  <p class="section-desc">
    This is the advertising profile Instagram constructed from your behaviour, device data,
    and information you've directly submitted. Advertisers use these fields to target you.
  </p>
  <div class="dossier">
    <div class="dossier-grid">
      <div>
        {"".join(f'<div class="dossier-field"><div class="label">{html.escape(k)}</div><div class="value">{html.escape(v)}</div></div>' for k, v in submitted.items()) if submitted else '<div class="dossier-field"><div class="label">Submitted data</div><div class="value" style="color:#999">None collected</div></div>'}
        {"".join(f'<div class="dossier-field"><div class="label">{html.escape(k)}</div><div class="value">{html.escape(v)}</div></div>' for k, v in subscription.items()) if subscription else ""}
        <div class="dossier-field"><div class="label">Total advertisers with access</div><div class="value">{len(top_advertisers)}</div></div>
        <div class="dossier-field"><div class="label">Off-platform trackers</div><div class="value">{len(off_meta_businesses)} companies</div></div>
      </div>
      <div>
        <div class="dossier-field"><div class="label">Behavioural categories assigned</div>
          <div class="tag-row">{"".join(f'<span class="tag">{html.escape(c)}</span>' for c in categories) if categories else '<span style="color:#999">None</span>'}</div>
        </div>
        <div class="dossier-field"><div class="label">Content in your feed that was ads</div><div class="value">{ads_pct}% of all content served</div></div>
        <div class="dossier-field"><div class="label">Advertiser concentration</div><div class="value">Top 5 advertisers = {top5_pct}% of your ads</div></div>
      </div>
    </div>
  </div>
  <div class="insight">
    Instagram categorises you based on your <strong>device type</strong>, <strong>network behaviour</strong>,
    and <strong>browsing patterns</strong> -- not just what you follow. These categories are sold
    to advertisers as targeting options without your explicit consent for each one.
  </div>
</div>

<div class="section reveal">
  <div class="section-number">02 -- Who pays to reach you</div>
  <h2>{len(top_advertisers)} advertisers bought access to your attention</h2>
  <p class="section-desc">Each bar represents a company that paid Instagram to place content in your feed.</p>
  <div class="card">
    <div class="card-label">Top 20 advertisers by frequency</div>
    <div class="chart-container tall"><canvas id="topAdvertisersChart"></canvas></div>
  </div>
  <div class="insight">
    <strong>{list(top_advertisers.keys())[0] if top_advertisers else "Unknown"}</strong> appeared
    in your feed <strong>{list(top_advertisers.values())[0] if top_advertisers else 0} times</strong>.
    The top 5 advertisers alone account for {top5_pct}% of all ads you were shown.
  </div>
  <div class="card">
    <div class="card-label">All {len(top_advertisers)} advertisers</div>
    <div class="data-list">{"".join(f'<div class="data-list-item"><span class="name">{html.escape(n)}</span><span class="ct">{c}</span></div>' for n, c in list(top_advertisers.items())[:80])}</div>
  </div>
</div>

<div class="section reveal">
  <div class="section-number">03 -- Your resistance</div>
  <h2>You hid or reported {len(ad_prefs)} ads</h2>
  <p class="section-desc">Every time you hide or report an ad, Instagram logs it.</p>
  <div class="grid-2">
    <div class="card"><div class="card-label">Actions over time</div><div class="chart-container"><canvas id="hiddenAdsTimeline"></canvas></div></div>
    <div class="card"><div class="card-label">Type of action</div><div class="chart-container"><canvas id="hiddenTypesChart"></canvas></div></div>
  </div>
  <div class="insight">
    Even when you reject an ad, the act of rejection becomes data. Instagram uses
    your <strong>hide</strong> and <strong>report</strong> signals to refine its model of what you'll
    tolerate -- optimising not for your comfort, but for the threshold just below your resistance.
  </div>
</div>

</div>

<div class="inv">
<div class="container">
<div class="section reveal" style="border:none;">
  <div class="section-number">04 -- Surveillance beyond the app</div>
  <h2>{len(off_meta_businesses)} companies shared your activity with Instagram</h2>
  <p class="section-desc">
    These businesses sent data about your behaviour on their websites and apps back to Meta.
    You were tracked across {sum(len(v) for v in off_meta_events.values())} interactions outside of Instagram.
  </p>
  <div class="grid-2">
    <div class="card"><div class="card-label">Data shared per company</div><div class="chart-container"><canvas id="offMetaBizChart"></canvas></div></div>
    <div class="card"><div class="card-label">What they tracked</div><div class="chart-container"><canvas id="offMetaTypesChart"></canvas></div></div>
  </div>
  <div class="card"><div class="card-label">When they tracked you</div><div class="chart-container short"><canvas id="offMetaTimeline"></canvas></div></div>
  <div class="insight">
    Meta's tracking pixel is embedded on millions of websites. When you visit <strong>{list(off_meta_by_biz.keys())[0] if off_meta_by_biz else "a website"}</strong>,
    search for a product, or view a page, that activity is sent to Instagram and linked to your profile --
    even when you're not logged in.
  </div>
</div>
</div>
</div>

<div class="container">

<div class="section reveal">
  <div class="section-number">05 -- Your behavioural fingerprint</div>
  <h2>Instagram logged {total_content:,} pieces of content you consumed</h2>
  <p class="section-desc">Every post you pause on, every video you watch -- it's recorded.</p>
  <div class="grid-3">
    <div class="card" style="text-align:center;padding:24px 16px;"><div style="font-size:2em;">{len(posts_viewed):,}</div><div style="font-size:0.6em;color:#999;text-transform:uppercase;letter-spacing:0.2em;margin-top:4px;">Posts tracked</div></div>
    <div class="card" style="text-align:center;padding:24px 16px;"><div style="font-size:2em;">{len(videos_watched):,}</div><div style="font-size:0.6em;color:#999;text-transform:uppercase;letter-spacing:0.2em;margin-top:4px;">Videos tracked</div></div>
    <div class="card" style="text-align:center;padding:24px 16px;"><div style="font-size:2em;">{len(ads_viewed):,}</div><div style="font-size:0.6em;color:#999;text-transform:uppercase;letter-spacing:0.2em;margin-top:4px;">Ads tracked</div></div>
  </div>
  <div class="card"><div class="card-label">Accounts you viewed most (posts)</div><div class="chart-container tall"><canvas id="topPostsChart"></canvas></div></div>
  <div class="card"><div class="card-label">Accounts you watched most (video)</div><div class="chart-container tall"><canvas id="topVideosChart"></canvas></div></div>
  <div class="insight">
    This data forms a <strong>behavioural fingerprint</strong> unique to you. Instagram uses it to
    predict what content will keep you on the platform longer, and which ads you're most
    likely to act on. Your attention is the product being optimised.
  </div>
</div>

</div>

<div class="footer">Generated locally from your Instagram data export. No data was sent anywhere. Your data never left your computer.</div>

<script>
  const obs = new IntersectionObserver((entries) => {{
    entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }});
  }}, {{ threshold: 0.1 }});
  document.querySelectorAll('.reveal').forEach(el => obs.observe(el));

  Chart.defaults.font.family = "'SF Mono', 'Consolas', 'Monaco', monospace";
  Chart.defaults.font.size = 11;
  Chart.defaults.color = '#999';
  Chart.defaults.borderColor = '#e0e0e0';

  const BK = '#000000';
  const GY = '#999999';
  const LG = {{ color: '#f0f0f0' }};
  const NG = {{ display: false }};

  function bw(n) {{
    const out = [];
    for (let i = 0; i < n; i++) {{
      const t = i / Math.max(n - 1, 1);
      const v = Math.round(t * 180);
      out.push(`rgb(${{v}},${{v}},${{v}})`);
    }}
    return out;
  }}

  new Chart(document.getElementById('topAdvertisersChart'), {{
    type: 'bar',
    data: {{ labels: {js_json(list(top_20_advertisers.keys()))}, datasets: [{{ data: {js_json(list(top_20_advertisers.values()))}, backgroundColor: bw({len(top_20_advertisers)}), borderRadius: 2 }}] }},
    options: {{ indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ grid: LG, ticks: {{ color: GY }} }}, y: {{ grid: NG, ticks: {{ color: BK }} }} }} }}
  }});

  new Chart(document.getElementById('hiddenAdsTimeline'), {{
    type: 'bar',
    data: {{ labels: {js_json(list(hidden_ads_timeline.keys()))}, datasets: [{{ data: {js_json(list(hidden_ads_timeline.values()))}, backgroundColor: BK, borderRadius: 2 }}] }},
    options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true, grid: LG, ticks: {{ color: GY }} }}, x: {{ grid: NG, ticks: {{ color: GY, maxRotation: 45 }} }} }} }}
  }});

  new Chart(document.getElementById('hiddenTypesChart'), {{
    type: 'doughnut',
    data: {{ labels: {js_json(list(hidden_event_types.keys()))}, datasets: [{{ data: {js_json(list(hidden_event_types.values()))}, backgroundColor: ['#000','#666','#999','#bbb','#ddd'], borderWidth: 0, spacing: 2 }}] }},
    options: {{ responsive: true, maintainAspectRatio: false, cutout: '60%', plugins: {{ legend: {{ position: 'bottom', labels: {{ padding: 16, usePointStyle: true, pointStyle: 'rectRounded' }} }} }} }}
  }});

  new Chart(document.getElementById('offMetaBizChart'), {{
    type: 'bar',
    data: {{ labels: {js_json(list(off_meta_by_biz.keys()))}, datasets: [{{ data: {js_json(list(off_meta_by_biz.values()))}, backgroundColor: '#fff', borderRadius: 2 }}] }},
    options: {{ indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ grid: {{ color: '#222' }}, ticks: {{ color: '#666' }} }}, y: {{ grid: NG, ticks: {{ color: '#aaa' }} }} }} }}
  }});

  new Chart(document.getElementById('offMetaTypesChart'), {{
    type: 'doughnut',
    data: {{ labels: {js_json(list(off_meta_event_types.keys()))}, datasets: [{{ data: {js_json(list(off_meta_event_types.values()))}, backgroundColor: ['#fff','#aaa','#666','#444','#333','#222'], borderWidth: 0, spacing: 2 }}] }},
    options: {{ responsive: true, maintainAspectRatio: false, cutout: '60%', plugins: {{ legend: {{ position: 'bottom', labels: {{ padding: 16, color: '#888', usePointStyle: true, pointStyle: 'rectRounded' }} }} }} }}
  }});

  new Chart(document.getElementById('offMetaTimeline'), {{
    type: 'line',
    data: {{ labels: {js_json(list(off_meta_timeline.keys()))}, datasets: [{{ data: {js_json(list(off_meta_timeline.values()))}, borderColor: '#fff', backgroundColor: 'rgba(255,255,255,0.05)', fill: true, tension: 0.3, pointRadius: 3, pointBackgroundColor: '#fff' }}] }},
    options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true, grid: {{ color: '#222' }}, ticks: {{ color: '#666' }} }}, x: {{ grid: NG, ticks: {{ color: '#666', maxRotation: 45 }} }} }} }}
  }});

  new Chart(document.getElementById('topPostsChart'), {{
    type: 'bar',
    data: {{ labels: {js_json(list(top_20_posts.keys()))}, datasets: [{{ data: {js_json(list(top_20_posts.values()))}, backgroundColor: bw({len(top_20_posts)}), borderRadius: 2 }}] }},
    options: {{ indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ grid: LG, ticks: {{ color: GY }} }}, y: {{ grid: NG, ticks: {{ color: BK }} }} }} }}
  }});

  new Chart(document.getElementById('topVideosChart'), {{
    type: 'bar',
    data: {{ labels: {js_json(list(top_20_videos.keys()))}, datasets: [{{ data: {js_json(list(top_20_videos.values()))}, backgroundColor: bw({len(top_20_videos)}), borderRadius: 2 }}] }},
    options: {{ indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ grid: LG, ticks: {{ color: GY }} }}, y: {{ grid: NG, ticks: {{ color: BK }} }} }} }}
  }});
</script>
</body>
</html>"""

    output_path.write_text(report_html, encoding="utf-8")
    return output_path


# -- Main --

BANNER = r"""
  ___           _                                ____        _
 |_ _|_ __  ___| |_ __ _  __ _ _ __ __ _ _ __ _|  _ \  __ _| |_ __ _
  | || '_ \/ __| __/ _` |/ _` | '__/ _` | '_ (_) | | |/ _` | __/ _` |
  | || | | \__ \ || (_| | (_| | | | (_| | | | | | |_| | (_| | || (_| |
 |___|_| |_|___/\__\__,_|\__, |_|  \__,_|_| |_|_|____/ \__,_|\__\__,_|
     Ads & Business       |___/                         Data Viewer
"""


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print(BANNER)

    data_path = sys.argv[1] if len(sys.argv) > 1 else None
    if not data_path:
        print("  Enter the path to your Instagram data export folder.")
        print("  (You can drag and drop the folder onto this window)\n")
        data_path = input("  Path: ").strip().strip('"').strip("'")

    root = Path(data_path)
    if not root.is_dir():
        print(f"\n  Error: '{root}' is not a valid directory.")
        try:
            input("\n  Press Enter to exit...")
        except EOFError:
            pass
        sys.exit(1)

    ads_biz = root / "ads_information" / "instagram_ads_and_businesses"
    ads_topics = root / "ads_information" / "ads_and_topics"
    off_meta_dir = root / "apps_and_websites_off_of_instagram" / "apps_and_websites"

    if not (root / "ads_information").is_dir():
        print(f"\n  Error: This doesn't look like an Instagram data export.")
        print(f"  Expected to find 'ads_information' folder inside: {root}")
        try:
            input("\n  Press Enter to exit...")
        except EOFError:
            pass
        sys.exit(1)

    print("  Parsing data...\n")

    ad_preferences = parse_ad_preferences(ads_biz / "ad_preferences.html")
    print(f"    Hidden/reported ads:     {len(ad_preferences)}")

    ads_viewed = parse_ads_viewed(ads_topics / "ads_viewed.html")
    print(f"    Ads viewed:              {len(ads_viewed)}")

    categories = parse_other_categories(ads_biz / "other_categories_used_to_reach_you.html")
    print(f"    Ad targeting categories: {len(categories)}")

    submitted_info = parse_submitted_info(ads_biz / "information_you've_submitted_to_advertisers.html")
    print(f"    Submitted info fields:   {len(submitted_info)}")

    subscription = parse_subscription(ads_biz / "subscription_for_no_ads.html")
    status = subscription.get("Your subscription status", "Unknown")
    print(f"    No-ads subscription:     {status}")

    off_meta_businesses = parse_off_meta_index(
        off_meta_dir / "your_activity_off_meta_technologies.html"
    )
    print(f"    Off-Meta businesses:     {len(off_meta_businesses)}")

    off_meta_events = {}
    detail_dir = off_meta_dir / "your_activity_off_meta_technologies"
    if detail_dir.is_dir():
        for i, biz_name in enumerate(off_meta_businesses):
            detail_file = detail_dir / f"{i}.html"
            events = parse_off_meta_detail(detail_file)
            if events:
                off_meta_events[biz_name] = events
    total_off_events = sum(len(v) for v in off_meta_events.values())
    print(f"    Off-Meta events:         {total_off_events}")

    posts_viewed = parse_posts_viewed(ads_topics / "posts_viewed.html")
    print(f"    Posts viewed:             {len(posts_viewed)}")

    videos_watched = parse_videos_watched(ads_topics / "videos_watched.html")
    print(f"    Videos watched:           {len(videos_watched)}")

    data = {
        "ad_preferences": ad_preferences,
        "ads_viewed": ads_viewed,
        "categories": categories,
        "submitted_info": submitted_info,
        "subscription": subscription,
        "off_meta_businesses": off_meta_businesses,
        "off_meta_events": off_meta_events,
        "posts_viewed": posts_viewed,
        "videos_watched": videos_watched,
    }

    output = root.parent / "instagram_ads_report.html"
    print(f"\n  Generating report...\n  -> {output}")
    generate_report(data, output)

    print("\n  Done! Opening in your browser...")
    webbrowser.open(output.as_uri())

    try:
        input("\n  Press Enter to exit...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
