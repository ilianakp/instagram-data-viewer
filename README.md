# Instagram Ads & Business Data Viewer

A standalone Windows executable that parses your Instagram data export and generates an interactive HTML dashboard visualizing how Instagram tracks and targets you with ads.

## What it shows

- **Summary stats** -- total ads viewed, unique advertisers, hidden ads, off-meta trackers
- **Your ad profile** -- info you've submitted to advertisers, subscription status, targeting categories
- **Top advertisers** -- who shows you the most ads (bar chart)
- **Hidden ads timeline** -- when you've hidden/reported ads over time
- **Content viewed** -- top accounts by posts and videos viewed
- **Off-Meta activity** -- which businesses share your activity with Instagram, event types, timeline

## Usage

### Option 1: Drag and drop
Drag your Instagram data export folder onto `InstaDataViewer.exe`.

### Option 2: Double-click
Double-click `InstaDataViewer.exe` and paste the path to your data folder when prompted.

### Option 3: Command line
```
InstaDataViewer.exe "C:\path\to\instagram-data-export"
```

The report opens automatically in your default browser.

## Getting your Instagram data

1. Go to Instagram Settings > Your Activity > Download Your Information
2. Select **HTML** format
3. Download and extract the archive
4. Point this tool at the extracted folder

## Building from source

Only needed if you want to modify the code. End users just run the exe.

Requires Python 3.9+.

```bash
pip install pyinstaller
python -m PyInstaller --onefile --console --name InstaDataViewer --add-data "chartjs.min.js;." instagram_ads_viewer.py
```

The exe will be in `dist/InstaDataViewer.exe`.
