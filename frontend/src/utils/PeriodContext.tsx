"use client";

import React, { createContext, useContext, useMemo, useState } from "react";
import { currentPeriod } from "./periods";

export interface PeriodContextValue {
  period: string;
  setPeriod: (p: string) => void;
}

const PeriodContext = createContext<PeriodContextValue | null>(null);

export function PeriodProvider({ children }: { children: React.ReactNode }) {
  const [period, setPeriod] = useState(currentPeriod());

  const value = useMemo<PeriodContextValue>(
    () => ({ period, setPeriod }),
    [period]
  );

  return <PeriodContext.Provider value={value}>{children}</PeriodContext.Provider>;
}

/** Hook to read/set the globally selected reporting period. */
export function usePeriod(): PeriodContextValue {
  const ctx = useContext(PeriodContext);
  if (!ctx) {
    throw new Error("usePeriod must be used within a PeriodProvider");
  }
  return ctx;
}
