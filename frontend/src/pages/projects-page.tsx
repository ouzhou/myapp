import { useCallback, useEffect, useState } from "react"
import { FolderKanban, TriangleAlert } from "lucide-react"

import { CreateProjectDialog } from "@/components/create-project-dialog"
import { RequirePerm } from "@/components/require-perm"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ApiError, listProjects, type Project } from "@/lib/api"
import { Perm } from "@/lib/permissions"
import { useSession } from "@/lib/session"

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  })
}

export function ProjectsPage() {
  return (
    <RequirePerm perm={Perm.PROJECT_READ}>
      <ProjectsBody />
    </RequirePerm>
  )
}

function ProjectsBody() {
  const { me, hasPerm } = useSession()
  const tenantId = me?.current_tenant?.id
  const [projects, setProjects] = useState<Project[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const page = await listProjects()
      setProjects(page.items)
      setTotal(page.total)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, tenantId])

  return (
    <>
      <div className="mb-2 flex items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl tracking-tight">项目</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {loading ? "加载中…" : `共 ${total} 个`}
          </p>
        </div>
        {hasPerm(Perm.PROJECT_WRITE) ? (
          <CreateProjectDialog onCreated={() => void load()} />
        ) : null}
      </div>

      {error ? (
        <Alert variant="destructive">
          <TriangleAlert />
          <AlertTitle>无法加载项目</AlertTitle>
          <AlertDescription>
            {error}
            <Button
              variant="ghost"
              size="sm"
              className="mt-2"
              onClick={() => void load()}
            >
              重试
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {!loading && !error && projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed py-16 text-center">
          <FolderKanban className="mb-3 size-8 text-muted-foreground" />
          <p className="text-sm font-medium">还没有项目</p>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">
            {hasPerm(Perm.PROJECT_WRITE)
              ? "新建一个，会写到当前租户。"
              : "当前角色只能查看项目，不能新建。"}
          </p>
        </div>
      ) : null}

      <ul className="grid gap-3">
        {projects.map((project) => (
          <li
            key={project.id}
            className="rounded-xl bg-card p-4 ring-1 ring-foreground/10"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-medium">{project.name}</p>
                {project.description ? (
                  <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                    {project.description}
                  </p>
                ) : null}
              </div>
              {project.status ? (
                <Badge variant="secondary">{project.status}</Badge>
              ) : (
                <Badge variant="outline">未设置</Badge>
              )}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              {formatTime(project.created_at)}
            </p>
          </li>
        ))}
      </ul>
    </>
  )
}
