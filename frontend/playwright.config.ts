import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    screenshot: "only-on-failure",
    trace: "retain-on-failure"
  },
  projects: [
    {
      name: "chromium",
      testIgnore: /(?:^|[\\/])ceo-[^\\/]*\.spec\.ts$/,
      use: { ...devices["Desktop Chrome"] }
    },
    {
      name: "ceo-chromium",
      testMatch: /(?:^|[\\/])ceo-[^\\/]*\.spec\.ts$/,
      use: { ...devices["Desktop Chrome"], baseURL: "http://127.0.0.1:4174" }
    }
  ],
  webServer: [
    {
      command: "pnpm exec vite --host 127.0.0.1 --port 4173 --strictPort",
      env: { VITE_CEO_DEMO: "false" },
      reuseExistingServer: false,
      url: "http://127.0.0.1:4173"
    },
    {
      command: "pnpm exec vite --host 127.0.0.1 --port 4174 --strictPort",
      env: { VITE_CEO_DEMO: "true" },
      reuseExistingServer: false,
      url: "http://127.0.0.1:4174"
    }
  ]
});
