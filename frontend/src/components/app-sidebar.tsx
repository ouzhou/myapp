import { NavLink, useLocation } from "react-router-dom"
import {
  ChevronsUpDown,
  FolderKanban,
  LogOut,
  Shield,
  Users,
} from "lucide-react"

import { toast } from "sonner"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import { ApiError } from "@/lib/api"
import { Perm } from "@/lib/permissions"
import { useSession } from "@/lib/session"

const NAV = [
  { title: "项目", to: "/", perm: Perm.PROJECT_READ, icon: FolderKanban },
  { title: "角色", to: "/roles", perm: Perm.ROLE_READ, icon: Shield },
  { title: "成员", to: "/members", perm: Perm.MEMBER_READ, icon: Users },
] as const

type AppSidebarProps = {
  onSignOut: () => void
}

export function AppSidebar({ onSignOut }: AppSidebarProps) {
  const { me, hasPerm, switchTenant } = useSession()
  const { isMobile } = useSidebar()
  const location = useLocation()
  const items = NAV.filter((item) => hasPerm(item.perm))
  const tenant = me?.current_tenant
  const initials = (me?.user.display_name || me?.user.email || "?").slice(0, 1)

  return (
    <Sidebar collapsible="icon" variant="inset">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            {me && me.tenants.length > 1 ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <SidebarMenuButton
                    size="lg"
                    className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                  >
                    <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                      {(tenant?.name ?? "m").slice(0, 1)}
                    </div>
                    <div className="grid flex-1 text-left text-sm leading-tight">
                      <span className="truncate font-medium">
                        {tenant?.name ?? "未加入租户"}
                      </span>
                      <span className="truncate text-xs text-muted-foreground">
                        myapp
                      </span>
                    </div>
                    <ChevronsUpDown className="ml-auto size-4" />
                  </SidebarMenuButton>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg"
                  align="start"
                  side={isMobile ? "bottom" : "right"}
                  sideOffset={4}
                >
                  <DropdownMenuLabel className="text-xs text-muted-foreground">
                    租户
                  </DropdownMenuLabel>
                  {me.tenants.map((row) => (
                    <DropdownMenuItem
                      key={row.id}
                      onClick={() => {
                        void switchTenant(row.id).catch((err) => {
                          toast.error(
                            err instanceof ApiError ? err.message : "切换失败",
                          )
                        })
                      }}
                    >
                      {row.name}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <SidebarMenuButton size="lg" className="pointer-events-none">
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                  {(tenant?.name ?? "m").slice(0, 1)}
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-medium">
                    {tenant?.name ?? "未加入租户"}
                  </span>
                  <span className="truncate text-xs text-muted-foreground">
                    myapp
                  </span>
                </div>
              </SidebarMenuButton>
            )}
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>工作台</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {items.map((item) => (
                <SidebarMenuItem key={item.to}>
                  <SidebarMenuButton
                    asChild
                    isActive={location.pathname === item.to}
                    tooltip={item.title}
                  >
                    <NavLink to={item.to}>
                      <item.icon />
                      <span>{item.title}</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                >
                  <Avatar className="size-8 rounded-lg">
                    <AvatarFallback className="rounded-lg">
                      {initials}
                    </AvatarFallback>
                  </Avatar>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-medium">
                      {me?.user.display_name ?? "未登录"}
                    </span>
                    <span className="truncate text-xs text-muted-foreground">
                      {me?.user.email}
                    </span>
                  </div>
                  <ChevronsUpDown className="ml-auto size-4" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg"
                side={isMobile ? "bottom" : "right"}
                align="end"
                sideOffset={4}
              >
                <DropdownMenuLabel className="p-0 font-normal">
                  <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                    <Avatar className="size-8 rounded-lg">
                      <AvatarFallback className="rounded-lg">
                        {initials}
                      </AvatarFallback>
                    </Avatar>
                    <div className="grid flex-1 text-left text-sm leading-tight">
                      <span className="truncate font-medium">
                        {me?.user.display_name}
                      </span>
                      <span className="truncate text-xs text-muted-foreground">
                        {me?.user.email}
                      </span>
                    </div>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onSignOut}>
                  <LogOut />
                  登出
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
