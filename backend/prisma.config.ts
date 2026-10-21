import { config } from "dotenv";
import { defineConfig, env } from "prisma/config";

// Same file used by Uvicorn. Shell variables take precedence.
config({ path: ".env.local" });

export default defineConfig({
  schema: "prisma/schema.prisma",
  migrations: { path: "prisma/migrations" },
  datasource: { url: process.env.DIRECT_URL || env("MIGRATION_DATABASE_URL") },
});
