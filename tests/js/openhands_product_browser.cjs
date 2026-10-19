// Run with a temporary Playwright install; never a product runtime dependency.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const key = fs.readFileSync(process.env.REMEDIATION_BROWSER_KEY_FILE, 'utf8').trim();
  const browser = await chromium.launch({headless: true, timeout: 20000,
    args: ['--no-sandbox', '--disable-dev-shm-usage']});
  try {
    const page = await browser.newPage();
    page.setDefaultTimeout(20000);
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(process.env.REMEDIATION_BROWSER_URL || 'http://127.0.0.1:8080');
    await page.locator('#key').fill(key);
    await page.getByRole('button', {name: 'Connect / refresh tasks', exact: true}).click();
    if (process.env.REMEDIATION_BROWSER_FAKE_ONLY === '1') {
      // Only the offline fixture uses this deliberately public test credential.
      assert.equal(key, 'k'.repeat(48));
      await page.locator('#sbri').selectOption('disabled');
      await page.locator('#delivery').selectOption('none');
      await page.locator('#submit button').click();
      await page.waitForFunction(() => document.querySelector('#selected').textContent.startsWith('task_'));
      await page.getByRole('button', {name: 'Authorize paid native run', exact: true}).waitFor({timeout: 30000});
      page.once('dialog', dialog => dialog.accept());
      await page.getByRole('button', {name: 'Authorize paid native run', exact: true}).click();
      await page.waitForFunction(() => document.querySelector('#details').textContent.includes('AUTHORIZED'));
      await page.getByRole('button', {name: 'Native activity', exact: true}).click();
      await page.waitForFunction(() => document.querySelector('#details').textContent.includes('initial-message'));
    } else {
      // Live check is read-only: never click submit, execute, or delivery.
      const task = process.env.REMEDIATION_BROWSER_TASK;
      await page.getByRole('button', {name: new RegExp(task)}).click();
      await page.getByRole('button', {name: 'Result and validation', exact: true}).click();
      await page.waitForFunction(() => document.querySelector('#details').textContent.includes('baselineCommit'));
      await page.getByRole('button', {name: 'Evidence', exact: true}).click();
      await page.getByRole('button', {name: 'Open baseline-report', exact: true}).click();
      await page.waitForFunction(() => document.querySelector('#details').textContent.includes('originalVulnerabilityFindings'));
    }
    assert.equal(await page.locator('#error').textContent(), '');
    assert.deepEqual(errors, []);
    if (process.env.REMEDIATION_BROWSER_SCREENSHOT) {
      await page.screenshot({path: process.env.REMEDIATION_BROWSER_SCREENSHOT, fullPage: true});
    }
    console.log(JSON.stringify({browser: 'chromium', journey: process.env.REMEDIATION_BROWSER_FAKE_ONLY === '1'
      ? 'offline UI submission, authorization and native activity' : 'live task retrieval and baseline evidence',
      javascriptErrors: errors.length, realModelRuns: 0, realGitHubMutations: 0, passed: true}));
  } finally {
    await browser.close();
  }
})().catch(e => {console.error(e);process.exitCode=1;});
