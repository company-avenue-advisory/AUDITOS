import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  output: "standalone",
  // Pin the workspace root to this directory. Without this, Next.js
  // auto-detects the root by walking up for the nearest lockfile and can
  // land on an unrelated one elsewhere on the machine (e.g. a stray
  // package-lock.json in a parent directory) - when that happens, the
  // standalone build nests server.js under the full inferred-root-relative
  // path instead of placing it at .next/standalone/server.js, breaking the
  // Docker CMD ["node", "server.js"]. Confirmed via a local build before
  // this fix - server.js landed at nested subdirectories instead.
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
