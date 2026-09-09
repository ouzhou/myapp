import { useEffect, useRef, type ReactNode } from "react"
import { useLogto } from "@logto/react"

import { configureApi } from "@/lib/auth"
import { LOGTO_RESOURCE } from "@/lib/logto"

export function ApiSession({ children }: { children: ReactNode }) {
  const { getAccessToken, isAuthenticated } = useLogto()
  const authRef = useRef({ getAccessToken, isAuthenticated })
  authRef.current = { getAccessToken, isAuthenticated }

  useEffect(() => {
    configureApi({
      getAccessToken: async () => {
        const current = authRef.current
        if (!current.isAuthenticated) {
          return undefined
        }
        return current.getAccessToken(LOGTO_RESOURCE)
      },
    })
  }, [])

  return children
}
