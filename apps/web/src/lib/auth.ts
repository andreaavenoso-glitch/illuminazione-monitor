"use client";

const TOKEN_KEY = "lpm.token";
const USER_KEY = "lpm.user";

export type AuthUser = {
  id: string;
  email: string;
  role: "admin" | "analyst" | "viewer";
  full_name: string | null;
};

export function setSession(token: string, user: AuthUser): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event("lpm-auth-changed"));
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  window.dispatchEvent(new Event("lpm-auth-changed"));
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function hasRole(user: AuthUser | null, ...roles: AuthUser["role"][]): boolean {
  if (!user) return false;
  const rank: Record<AuthUser["role"], number> = { viewer: 1, analyst: 2, admin: 3 };
  const min = Math.min(...roles.map((r) => rank[r]));
  return rank[user.role] >= min;
}
