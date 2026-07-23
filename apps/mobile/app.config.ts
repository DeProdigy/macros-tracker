import type { ConfigContext, ExpoConfig } from "expo/config";

// Dynamic config layered on top of app.json — injects env-driven values.
// EXPO_PUBLIC_API_URL is inlined into the JS bundle at build time; surfacing it
// in `extra` also makes it readable via Constants.expoConfig?.extra?.apiUrl.
export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: config.name ?? "Macros Tracker",
  slug: config.slug ?? "macros-tracker",
  extra: {
    ...config.extra,
    apiUrl: process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000",
  },
});
