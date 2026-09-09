import { useState, type ReactNode } from "react"
import { useLogto } from "@logto/react"
import { Navigate, Outlet, useOutletContext } from "react-router-dom"
import { toast } from "sonner"

import { AppShell } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import { setTenantId } from "@/lib/auth"
import { callbackUri, postLogoutUri } from "@/lib/logto"
import { SessionProvider, useSession } from "@/lib/session"

const TEST_ACCOUNTS = [
  { username: "demo_platform", note: "平台管理员" },
  { username: "demo_admin", note: "租户管理员" },
  { username: "demo_member", note: "普通成员" },
] as const

export type AuthedOutletContext = {
  onSignOut: () => void
}

function TestAccounts() {
  const password = import.meta.env.VITE_LOGTO_SEED_PASSWORD
  return (
    <div className="mt-4 rounded-lg bg-muted/60 px-3 py-2.5 text-sm">
      <p className="text-xs text-muted-foreground">测试账号</p>
      <ul className="mt-2 grid gap-2">
        {TEST_ACCOUNTS.map((account) => (
          <li key={account.username} className="leading-5">
            <p className="text-xs text-muted-foreground">{account.note}</p>
            <p className="font-mono text-xs">账号 {account.username}</p>
            <p className="font-mono text-xs">
              密码 {password ?? "见 VITE_LOGTO_SEED_PASSWORD"}
            </p>
          </li>
        ))}
      </ul>
    </div>
  )
}

function SignInScreen() {
  const { signIn } = useLogto()
  const [busy, setBusy] = useState(false)

  async function onSignIn() {
    setBusy(true)
    try {
      await signIn(callbackUri())
    } catch {
      setBusy(false)
      toast.error("无法跳转到登录页")
    }
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-background p-6">
      <div className="w-full max-w-sm rounded-xl bg-card p-6 ring-1 ring-foreground/10">
        <h1 className="font-heading text-xl tracking-tight">myapp</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          使用 Logto 登录后才能访问工作台。
        </p>
        <TestAccounts />
        <Button className="mt-6 w-full" disabled={busy} onClick={() => void onSignIn()}>
          {busy ? "正在跳转…" : "登录"}
        </Button>
      </div>
    </div>
  )
}

export function AuthedLayout() {
  const { isAuthenticated, isLoading: logtoLoading, signOut } = useLogto()

  async function onSignOut() {
    setTenantId(undefined)
    await signOut(postLogoutUri())
  }

  if (logtoLoading && !isAuthenticated) {
    return (
      <main className="flex min-h-svh items-center justify-center">
        <p className="text-sm text-muted-foreground">正在检查登录状态…</p>
      </main>
    )
  }

  if (!isAuthenticated) {
    return <SignInScreen />
  }

  return (
    <SessionProvider>
      <Outlet context={{ onSignOut: () => void onSignOut() } satisfies AuthedOutletContext} />
    </SessionProvider>
  )
}

function SessionGate({ children }: { children: ReactNode }) {
  const { loading, error, refresh } = useSession()
  if (loading) {
    return (
      <main className="flex min-h-svh items-center justify-center">
        <p className="text-sm text-muted-foreground">加载中…</p>
      </main>
    )
  }
  if (error) {
    return (
      <main className="flex min-h-svh items-center justify-center p-6">
        <div className="text-sm">
          <p>{error}</p>
          <button type="button" className="mt-2 underline" onClick={() => void refresh()}>
            重试
          </button>
        </div>
      </main>
    )
  }
  return children
}

export function TenantLayout() {
  const { onSignOut } = useOutletContext<AuthedOutletContext>()
  const { me } = useSession()
  return (
    <SessionGate>
      {me?.user.is_platform_admin ? (
        <Navigate to="/platform" replace />
      ) : (
        <AppShell onSignOut={onSignOut} />
      )}
    </SessionGate>
  )
}
