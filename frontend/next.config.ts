import type { NextConfig } from "next";

// NOTE (C1): `cacheComponents` (and `partialPrefetching`, which requires it) were turned OFF.
// ASTRA's pages are almost entirely client-side (URL-param driven viewer, polling, canvas), and
// cacheComponents would keep hidden routes alive via <Activity> (polling/animation state would
// leak across navigation) and force Suspense/dynamic-data rules on every server component.
const nextConfig: NextConfig = {
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
