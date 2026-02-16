/**
 * birdbird Web Viewer Configuration
 *
 * IMPORTANT: You must edit this file before deploying the viewer.
 * Replace the placeholder values below with your actual site information.
 */

// Only set config if not already defined (allows config.local.js to take precedence)
if (typeof window.BIRDBIRD_CONFIG === 'undefined') {
  window.BIRDBIRD_CONFIG = {
  // REQUIRED: Your R2/S3 bucket public URL
  // Find this in your Cloudflare R2 dashboard under Settings → Public Access
  // Example: 'https://pub-abc123def456.r2.dev'
  r2BaseUrl: 'https://REPLACE-WITH-YOUR-BUCKET.r2.dev',

  // Site title displayed in header and browser tab
  siteName: 'Bird Feeder Highlights',

  // Subtitle shown under the site title
  // Example: 'Bristol, UK • Automated bird activity highlights'
  siteSubtitle: 'Your Location • Automated bird activity highlights from motion-triggered clips',

  // Optional: Analytics code snippet (leave empty if not using analytics)
  // Example: Umami Cloud, Google Analytics, Plausible, etc.
  // This will be injected at the end of <body>
  analytics: '<script defer src="https://cloud.umami.is/script.js" data-website-id="b289f3b8-d85a-41a3-b971-54b506146e17"></script>'
  };
}
