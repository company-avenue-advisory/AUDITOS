"use client";

import { useEffect, useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Module-level cache so repeated mounts don't refetch the tenant name.
let cachedTenantName: string | null = null;
let inFlightRequest: Promise<string | null> | null = null;

function fetchTenantName(): Promise<string | null> {
  if (cachedTenantName !== null) return Promise.resolve(cachedTenantName);
  if (inFlightRequest) return inFlightRequest;

  const token = localStorage.getItem("token");
  if (!token) return Promise.resolve(null);

  inFlightRequest = fetch(`${API_BASE_URL}/api/me/tenant`, {
    headers: { Authorization: `Bearer ${token}` },
  })
    .then((r) => r.json())
    .then((data) => {
      const name = data?.tenant?.name ?? null;
      if (name) cachedTenantName = name;
      return name;
    })
    .catch(() => null)
    .finally(() => {
      inFlightRequest = null;
    });

  return inFlightRequest;
}

/** Returns the current tenant (firm) name, or null while loading/unavailable. */
export function useTenantName(): string | null {
  const [tenantName, setTenantName] = useState<string | null>(cachedTenantName);

  useEffect(() => {
    if (cachedTenantName !== null) {
      setTenantName(cachedTenantName);
      return;
    }
    fetchTenantName().then((name) => {
      if (name) setTenantName(name);
    });
  }, []);

  return tenantName;
}
