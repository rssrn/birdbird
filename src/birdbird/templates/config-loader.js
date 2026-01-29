/**
 * birdbird Configuration Loader
 *
 * Applies configuration from config.js to the page and warns if placeholders are detected.
 *
 * @author Claude Sonnet 4.5 Anthropic
 */

(function() {
  'use strict';

  // Check if config is loaded
  if (typeof window.BIRDBIRD_CONFIG === 'undefined') {
    console.error('BIRDBIRD_CONFIG not found. Make sure config.js is loaded before config-loader.js');
    return;
  }

  const config = window.BIRDBIRD_CONFIG;

  // Detect placeholder values that need to be replaced
  const placeholders = [];

  if (!config.r2BaseUrl || config.r2BaseUrl.includes('REPLACE-WITH-YOUR-BUCKET')) {
    placeholders.push('R2 bucket URL (r2BaseUrl)');
  }

  if (config.siteSubtitle && config.siteSubtitle.includes('Your Location')) {
    placeholders.push('Site subtitle (siteSubtitle)');
  }

  // Make R2_BASE_URL available immediately for index.html
  // (needs to be available before the main script runs)
  if (config.r2BaseUrl && typeof window !== 'undefined') {
    window.R2_BASE_URL = config.r2BaseUrl;
  }

  // Apply configuration to page when DOM is ready
  document.addEventListener('DOMContentLoaded', function() {
    applyConfig();

    // Show warning overlay if placeholders detected
    if (placeholders.length > 0) {
      showConfigWarning(placeholders);
    }

    // Inject analytics if provided
    if (config.analytics && config.analytics.trim()) {
      injectAnalytics(config.analytics);
    }
  });

  function applyConfig() {
    // Update page title
    if (config.siteName) {
      const titleElement = document.querySelector('title');
      if (titleElement && !titleElement.textContent.includes(' - ')) {
        // Only update if it's the main page title, not subpages
        const currentTitle = titleElement.textContent;
        if (currentTitle === 'Bird Feeder Highlights') {
          titleElement.textContent = config.siteName;
        } else {
          // For subpages, replace the site name part
          titleElement.textContent = currentTitle.replace('Bird Feeder Highlights', config.siteName);
        }
      }
    }

    // Update header title
    const headerTitle = document.querySelector('header h1');
    if (headerTitle && headerTitle.textContent === 'Bird Feeder Highlights') {
      headerTitle.textContent = config.siteName;
    }

    // Update subtitle
    const subtitle = document.querySelector('header .subtitle');
    if (subtitle && config.siteSubtitle) {
      subtitle.textContent = config.siteSubtitle;
    }

    // Update footer
    const footer = document.querySelector('footer');
    if (footer && config.siteName) {
      // Replace "Powered by birdbird" with custom site name if different
      footer.innerHTML = footer.innerHTML.replace(
        'Powered by birdbird',
        `Powered by birdbird`
      );
    }
  }

  function injectAnalytics(code) {
    const script = document.createElement('div');
    script.innerHTML = code;
    document.body.appendChild(script);
  }

  function showConfigWarning(missingItems) {
    const warning = document.createElement('div');
    warning.id = 'config-warning';
    warning.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.9);
      z-index: 10000;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    `;

    const box = document.createElement('div');
    box.style.cssText = `
      background: white;
      padding: 30px;
      border-radius: 8px;
      max-width: 600px;
      box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
    `;

    const title = document.createElement('h2');
    title.textContent = '⚠️ Configuration Required';
    title.style.cssText = 'margin-top: 0; color: #d97706;';

    const message = document.createElement('p');
    message.style.cssText = 'line-height: 1.6; color: #333;';
    message.innerHTML = `
      This birdbird viewer needs to be configured before use.
      Please edit <code style="background: #f3f4f6; padding: 2px 6px; border-radius: 3px;">config.js</code>
      and update the following placeholder values:
    `;

    const list = document.createElement('ul');
    list.style.cssText = 'margin: 15px 0; color: #666;';
    missingItems.forEach(item => {
      const li = document.createElement('li');
      li.textContent = item;
      li.style.cssText = 'margin: 8px 0;';
      list.appendChild(li);
    });

    const instructions = document.createElement('p');
    instructions.style.cssText = 'margin-top: 20px; padding: 15px; background: #f9fafb; border-left: 4px solid #3b82f6; color: #555; font-size: 0.9em; line-height: 1.5;';
    instructions.innerHTML = `
      <strong>How to fix:</strong><br>
      1. Open <code>config.js</code> in your deployment folder<br>
      2. Replace placeholder values with your actual settings<br>
      3. Redeploy or refresh the page
    `;

    const closeButton = document.createElement('button');
    closeButton.textContent = 'Dismiss (for now)';
    closeButton.style.cssText = `
      margin-top: 20px;
      padding: 10px 20px;
      background: #6b7280;
      color: white;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-size: 14px;
    `;
    closeButton.addEventListener('click', function() {
      warning.remove();
    });

    box.appendChild(title);
    box.appendChild(message);
    box.appendChild(list);
    box.appendChild(instructions);
    box.appendChild(closeButton);
    warning.appendChild(box);

    document.body.appendChild(warning);
  }
})();
