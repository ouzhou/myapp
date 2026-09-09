import { type ReactNode } from "react"
import { TriangleAlert } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { useSession } from "@/lib/session"

export function RequirePerm({
  perm,
  children,
}: {
  perm: string
  children: ReactNode
}) {
  const { hasPerm, me, loading } = useSession()
  if (loading) {
    return null
  }
  if (!me?.current_tenant) {
    return (
      <Alert>
        <TriangleAlert />
        <AlertTitle>还没有租户</AlertTitle>
        <AlertDescription>
          Logto 只负责认证。要使用工作台，需要有人把这个账号拉进租户并授角色。
        </AlertDescription>
      </Alert>
    )
  }
  if (!hasPerm(perm)) {
    return (
      <Alert>
        <TriangleAlert />
        <AlertTitle>没有权限</AlertTitle>
        <AlertDescription>当前角色看不到这个页面。</AlertDescription>
      </Alert>
    )
  }
  return children
}
