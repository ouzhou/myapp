import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { ApiError, createProject } from "@/lib/api"

type CreateProjectDialogProps = {
  onCreated: () => void
}

export function CreateProjectDialog({ onCreated }: CreateProjectDialogProps) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [status, setStatus] = useState("none")
  const [submitting, setSubmitting] = useState(false)

  function reset() {
    setName("")
    setDescription("")
    setStatus("none")
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      toast.error("请填写项目名称")
      return
    }

    setSubmitting(true)
    try {
      const project = await createProject({
        name: trimmed,
        description: description.trim() || null,
        status: status === "none" ? null : status,
      })
      toast.success(`已创建「${project.name}」`)
      reset()
      setOpen(false)
      onCreated()
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "创建失败"
      toast.error(message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          reset()
        }
        setOpen(next)
      }}
    >
      <DialogTrigger asChild>
        <Button>新建项目</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>新建项目</DialogTitle>
            <DialogDescription>
              写入当前租户。名称在租户内不能重复。
            </DialogDescription>
          </DialogHeader>
          <FieldGroup className="py-4">
            <Field>
              <FieldLabel htmlFor="project-name">名称</FieldLabel>
              <Input
                id="project-name"
                name="name"
                autoComplete="off"
                placeholder="例如：中文情感标注"
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={255}
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="project-description">描述</FieldLabel>
              <Textarea
                id="project-description"
                name="description"
                placeholder="可选"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="project-status">状态</FieldLabel>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger id="project-status" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">未设置</SelectItem>
                  <SelectItem value="draft">draft</SelectItem>
                  <SelectItem value="active">active</SelectItem>
                </SelectContent>
              </Select>
            </Field>
          </FieldGroup>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "创建中…" : "创建"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
