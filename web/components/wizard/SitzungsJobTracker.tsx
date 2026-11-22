"use client";

import { useEffect } from "react";
import { api } from "@/lib/api";
import { verfolgeSitzungsJobs } from "@/lib/analyse-lauf";

/** Restarts running analysis jobs from the session after a tab reload, on every page (not only the start page). */
export function SitzungsJobTracker() {
  useEffect(() => { verfolgeSitzungsJobs(api); }, []);
  return null;
}
