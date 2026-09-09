import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

import { ApiError, getMe, switchCurrentTenant, type Me } from "@/lib/api"
import { setTenantId } from "@/lib/auth"

type SessionValue = {
  me: Me | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  switchTenant: (tenantId: string) => Promise<void>
  hasPerm: (perm: string) => boolean
}

const SessionContext = createContext<SessionValue | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const profile = await getMe()
      setMe(profile)
      setTenantId(profile.current_tenant?.id)
    } catch (err) {
      setMe(null)
      setTenantId(undefined)
      setError(err instanceof ApiError ? err.message : "加载失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const switchTenant = useCallback(async (tenantId: string) => {
    const profile = await switchCurrentTenant(tenantId)
    setMe(profile)
    setTenantId(profile.current_tenant?.id)
  }, [])

  const hasPerm = useCallback(
    (perm: string) => Boolean(me?.permissions.includes(perm)),
    [me],
  )

  const value = useMemo(
    () => ({ me, loading, error, refresh, switchTenant, hasPerm }),
    [me, loading, error, refresh, switchTenant, hasPerm],
  )

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  )
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext)
  if (!ctx) {
    throw new Error("useSession must be used within SessionProvider")
  }
  return ctx
}
