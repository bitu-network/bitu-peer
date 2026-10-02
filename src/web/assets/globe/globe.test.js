// file: src/web/assets/globe/globe.test.js
import { test, expect } from '@playwright/test';

test('renders cesium-globe element', async ({ page }) => {
  await page.setContent(`
    <script type="module" src="./globe.js"></script>
    <cesium-globe style="width: 400px; height: 400px;"></cesium-globe>
  `);
  const globe = page.locator('cesium-globe');
  await expect(globe).toBeVisible();
});