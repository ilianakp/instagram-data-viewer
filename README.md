# Instagram Surveillance Report

A local, browser-based tool that parses your Instagram data export and reveals the advertising profile Instagram built from your activity -- the categories they assigned you and the companies tracking you beyond the app.

**Everything runs in your browser. No data is uploaded anywhere.**

## Use it

Open `index.html` in a Chromium browser (Chrome, Edge, Brave, Opera), click **[ select folder ]**, and point it at your Instagram data export folder.

Or visit the live site: https://ilianakp.github.io/instagram-data-viewer/

## What it shows

- **Your profile** -- info you've submitted to advertisers, targeting categories, advertiser concentration
- **Who pays to reach you** -- every company that bought ad space in your feed
- **Your resistance** -- timeline of ads you hid or reported
- **Surveillance beyond the app** -- off-Meta businesses that shared your activity back to Instagram
- **Your behavioural fingerprint** -- accounts you viewed and videos you watched most

## Getting your Instagram data

1. In Instagram, tap the **hamburger icon** (bottom-left) then **Settings**
2. Click **Accounts Centre** > **Your information and permissions**
3. Click **Export your information** > **Create export**
4. Select the profile you want to export and click **Next**
5. Select **Export to device**
6. Customise: choose the info, date range, set **Format: HTML**, media quality, notification email
7. Click **Start export**
8. When Instagram emails you the file, download and unzip it
9. Point this tool at the unzipped folder

## Browser requirement

Uses the [File System Access API](https://developer.mozilla.org/en-US/docs/Web/API/File_System_Access_API) to read your folder locally. Currently Chromium-only (Firefox/Safari don't support it yet).
