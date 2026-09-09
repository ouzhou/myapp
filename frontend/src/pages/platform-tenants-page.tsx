import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { Building2, TriangleAlert } from "lucide-react"

import { CreateTenantDialog } from "@/components/create-tenant-dialog"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  ApiError,
  listTenants,
  updateTenantStatus,
  type Tenant,
} from "@/lib/api"

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  })
}

function statusLabel(status: string): string {
  if (status === "active") {
    return "正常"
  }
  if (status === "disabled") {
    return "已停用"
  }
  return status
}

export function PlatformTenantsPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const page = await listTenants()
      setTenants(page.items)
      setTotal(page.total)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function onToggleStatus(tenant: Tenant) {
    const next = tenant.status === "active" ? "disabled" : "active"
    setBusyId(tenant.id)
    try {
      await updateTenantStatus(tenant.id, next)
      toast.success(next === "disabled" ? `已停用「${tenant.name}」` : `已启用「${tenant.name}」`)
      await load()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "操作失败")
    } finally {
      setBusyId(null)
    }
  }

  return (
    <>
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl tracking-tight">租户</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {loading ? "加载中…" : `共 ${total} 个`}
          </p>
        </div>
        <CreateTenantDialog onCreated={() => void load()} />
      </div>

      {error ? (
        <Alert variant="destructive">
          <TriangleAlert />
          <AlertTitle>无法加载租户</AlertTitle>
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

      {!loading && !error && tenants.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed py-16 text-center">
          <Building2 className="mb-3 size-8 text-muted-foreground" />
          <p className="text-sm font-medium">还没有租户</p>
        </div>
      ) : null}

      {tenants.length > 0 ? (
        <div className="overflow-hidden rounded-xl ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>编码</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>创建时间</TableHead>
                <TableHead className="w-24">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tenants.map((tenant) => (
                <TableRow key={tenant.id}>
                  <TableCell className="font-medium">{tenant.name}</TableCell>
                  <TableCell className="font-mono text-sm">{tenant.slug}</TableCell>
                  <TableCell>
                    <Badge
                      variant={tenant.status === "active" ? "secondary" : "outline"}
                    >
                      {statusLabel(tenant.status)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatTime(tenant.created_at)}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busyId === tenant.id}
                      onClick={() => void onToggleStatus(tenant)}
                    >
                      {tenant.status === "active" ? "停用" : "启用"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
    </>
  )
}
