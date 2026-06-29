import { Pool } from "pg";

import { env } from "../config/env";

export const pool = new Pool(env.db);

export async function checkDb(): Promise<boolean> {
  try {
    await pool.query("SELECT 1");
    return true;
  } catch {
    return false;
  }
}
