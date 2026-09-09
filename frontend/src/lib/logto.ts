import { UserScope, type LogtoConfig } from "@logto/react"

function requiredEnv(name: keyof ImportMetaEnv): string {
  const value = import.meta.env[name]
  if (!value) {
    throw new Error(`缺少环境变量 ${name}`)
  }
  return value
}

export const LOGTO_RESOURCE = requiredEnv("VITE_LOGTO_RESOURCE")

export const logtoConfig: LogtoConfig = {
  endpoint: requiredEnv("VITE_LOGTO_ENDPOINT"),
  appId: requiredEnv("VITE_LOGTO_APP_ID"),
  resources: [LOGTO_RESOURCE],
  scopes: [UserScope.Email, UserScope.Profile],
}

export function callbackUri(): string {
  return `${window.location.origin}/callback`
}

export function postLogoutUri(): string {
  return `${window.location.origin}/`
}
