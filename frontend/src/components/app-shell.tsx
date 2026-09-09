import { Outlet, useLocation } from "react-router-dom"

import { AppSidebar } from "@/components/app-sidebar"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb"
import { Separator } from "@/components/ui/separator"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { useSession } from "@/lib/session"

const TITLES: Record<string, string> = {
  "/": "项目",
  "/roles": "角色",
  "/members": "成员",
}

type AppShellProps = {
  onSignOut: () => void
}

export function AppShell({ onSignOut }: AppShellProps) {
  const location = useLocation()
  const { loading, error, refresh } = useSession()
  const title = TITLES[location.pathname] ?? "工作台"

  return (
    <SidebarProvider>
      <AppSidebar onSignOut={onSignOut} />
      <SidebarInset>
        <header className="flex h-16 shrink-0 items-center gap-2">
          <div className="flex items-center gap-2 px-4">
            <SidebarTrigger className="-ml-1" />
            <Separator
              orientation="vertical"
              className="mr-2 data-[orientation=vertical]:h-4"
            />
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbPage>{title}</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </div>
        </header>
        <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">加载中…</p>
          ) : error ? (
            <div className="rounded-xl border p-4 text-sm">
              <p>{error}</p>
              <button
                type="button"
                className="mt-2 text-sm underline"
                onClick={() => void refresh()}
              >
                重试
              </button>
            </div>
          ) : (
            <Outlet />
          )}
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
