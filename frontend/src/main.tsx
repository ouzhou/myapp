import { createRoot } from "react-dom/client"
import { LogtoProvider } from "@logto/react"
import { ThemeProvider } from "next-themes"
import { BrowserRouter, Route, Routes } from "react-router-dom"

import "./index.css"
import { AuthedLayout, TenantLayout } from "./App.tsx"
import { ApiSession } from "@/components/api-session"
import { PlatformLayout } from "@/components/platform-shell"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { logtoConfig } from "@/lib/logto"
import { CallbackPage } from "@/pages/callback-page"
import { MembersPage } from "@/pages/members-page"
import { PlatformTenantsPage } from "@/pages/platform-tenants-page"
import { ProjectsPage } from "@/pages/projects-page"
import { RolesPage } from "@/pages/roles-page"

createRoot(document.getElementById("root")!).render(
  <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
    <TooltipProvider>
      <LogtoProvider config={logtoConfig}>
        <BrowserRouter>
          <ApiSession>
            <Routes>
              <Route path="/callback" element={<CallbackPage />} />
              <Route element={<AuthedLayout />}>
                <Route path="/platform" element={<PlatformLayout />}>
                  <Route index element={<PlatformTenantsPage />} />
                </Route>
                <Route path="/" element={<TenantLayout />}>
                  <Route index element={<ProjectsPage />} />
                  <Route path="roles" element={<RolesPage />} />
                  <Route path="members" element={<MembersPage />} />
                </Route>
              </Route>
            </Routes>
          </ApiSession>
        </BrowserRouter>
        <Toaster position="top-center" />
      </LogtoProvider>
    </TooltipProvider>
  </ThemeProvider>,
)
