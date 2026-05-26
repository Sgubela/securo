import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { currencies as currenciesApi, workspaces as workspacesApi } from '@/lib/api'
import { useAuth } from '@/contexts/auth-context'
import { useWorkspace } from '@/contexts/workspace-context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { PageHeader } from '@/components/page-header'
import { Plus, Save, Trash2, Users } from 'lucide-react'
import type { WorkspaceMember, WorkspaceRole } from '@/types'

function labelForRole(role: WorkspaceRole, t: (key: string) => string): string {
  return {
    owner: t('workspace.roleOwner'),
    editor: t('workspace.roleEditor'),
    viewer: t('workspace.roleViewer'),
    manager: t('workspace.roleManager'),
  }[role]
}

function hintForRole(role: WorkspaceRole, t: (key: string) => string): string {
  return {
    owner: t('workspace.roleOwnerHint'),
    editor: t('workspace.roleEditorHint'),
    viewer: t('workspace.roleViewerHint'),
    manager: t('workspace.roleManagerHint'),
  }[role]
}

export default function WorkspaceSettingsPage() {
  const { t, i18n } = useTranslation()
  const { current, canManage, refresh } = useWorkspace()
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()

  const [editName, setEditName] = useState('')
  const [editCurrency, setEditCurrency] = useState('')
  const [editLocale, setEditLocale] = useState('')
  const [inviteOpen, setInviteOpen] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [invitePassword, setInvitePassword] = useState('')
  const [inviteRole, setInviteRole] = useState<WorkspaceRole>('editor')
  const [removeTarget, setRemoveTarget] = useState<WorkspaceMember | null>(null)

  useEffect(() => {
    if (!current) return
    setEditName(current.name)
    setEditCurrency(current.default_currency)
    setEditLocale(current.locale ?? '')
  }, [current?.id, current?.name, current?.default_currency, current?.locale])

  const membersQuery = useQuery({
    queryKey: ['workspace-members', current?.id],
    queryFn: () => (current ? workspacesApi.listMembers(current.id) : Promise.resolve([])),
    enabled: !!current,
  })

  const { data: supportedCurrencies } = useQuery({
    queryKey: ['currencies'],
    queryFn: currenciesApi.list,
    staleTime: Infinity,
  })

  const updateMutation = useMutation({
    mutationFn: () => {
      if (!current) throw new Error('No workspace')
      return workspacesApi.update(current.id, {
        name: editName,
        default_currency: editCurrency,
        locale: editLocale || (null as unknown as string),
      })
    },
    onSuccess: () => {
      toast.success(t('workspace.saveSuccess'))
      void refresh()
    },
    onError: (e: unknown) => {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : t('workspace.saveError'))
      toast.error(detail)
    },
  })

  const inviteMutation = useMutation({
    mutationFn: () => {
      if (!current) throw new Error('No workspace')
      return workspacesApi.invite(current.id, {
        email: inviteEmail.trim(),
        role: inviteRole,
        password: invitePassword || undefined,
      })
    },
    onSuccess: () => {
      toast.success(t('workspace.addSuccess'))
      setInviteOpen(false)
      setInviteEmail('')
      setInvitePassword('')
      setInviteRole('editor')
      queryClient.invalidateQueries({ queryKey: ['workspace-members', current?.id] })
    },
    onError: (e: unknown) => {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : 'Failed')
      toast.error(detail)
    },
  })

  const removeMutation = useMutation({
    mutationFn: (member: WorkspaceMember) => {
      if (!current) throw new Error('No workspace')
      return workspacesApi.removeMember(current.id, member.user_id)
    },
    onSuccess: () => {
      toast.success(t('workspace.removeSuccess'))
      setRemoveTarget(null)
      queryClient.invalidateQueries({ queryKey: ['workspace-members', current?.id] })
    },
    onError: (e: unknown) => {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : 'Failed')
      toast.error(detail)
    },
  })

  const roleChangeMutation = useMutation({
    mutationFn: ({ member, role }: { member: WorkspaceMember; role: WorkspaceRole }) => {
      if (!current) throw new Error('No workspace')
      return workspacesApi.changeRole(current.id, member.user_id, role)
    },
    onSuccess: () => {
      toast.success(t('workspace.roleUpdated'))
      queryClient.invalidateQueries({ queryKey: ['workspace-members', current?.id] })
    },
    onError: (e: unknown) => {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : 'Failed')
      toast.error(detail)
    },
  })

  if (!current) {
    return (
      <div className="container max-w-4xl py-8 space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }

  const members = membersQuery.data ?? []
  const isManaged = !!current.managed_by_user_id
  const isManagerSelf = isManaged && current.managed_by_user_id === currentUser?.id

  const localeOptions: Array<{ value: string; label: string }> = [
    { value: '', label: '—' },
    { value: 'en', label: 'English' },
    { value: 'pt-BR', label: 'Português (BR)' },
  ]

  return (
    <div className="container max-w-4xl py-8 space-y-6">
      <PageHeader
        title={t('workspace.settingsTitle')}
        description={t('workspace.settingsDescription')}
      />

      {/* Workspace details */}
      <section className="space-y-4 rounded-lg border bg-card p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">{t('workspace.details')}</h2>
          {isManaged && (
            <Badge variant="secondary" className="text-[11px]">
              {isManagerSelf
                ? t('workspace.youManageThis')
                : t('workspace.externallyManaged')}
            </Badge>
          )}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="ws-name" className="text-[13px]">
              {t('workspace.name')}
            </Label>
            <Input
              id="ws-name"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              disabled={!canManage}
              maxLength={100}
              className="h-10 rounded-lg"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ws-currency" className="text-[13px]">
              {t('workspace.defaultCurrency')}
            </Label>
            <select
              id="ws-currency"
              value={editCurrency}
              onChange={(e) => setEditCurrency(e.target.value)}
              disabled={!canManage}
              className="w-full h-10 rounded-lg border border-input bg-background px-3 text-sm disabled:opacity-60"
            >
              {(supportedCurrencies ?? [{ code: editCurrency, symbol: editCurrency, name: editCurrency, flag: '' }]).map((c) => (
                <option key={c.code} value={c.code}>
                  {c.flag} {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ws-locale" className="text-[13px]">
              {t('workspace.locale')}
            </Label>
            <select
              id="ws-locale"
              value={editLocale}
              onChange={(e) => setEditLocale(e.target.value)}
              disabled={!canManage}
              className="w-full h-10 rounded-lg border border-input bg-background px-3 text-sm disabled:opacity-60"
            >
              {localeOptions.map((opt) => (
                <option key={opt.value || 'empty'} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        {canManage && (
          <div className="flex justify-end pt-1">
            <Button
              onClick={() => updateMutation.mutate()}
              disabled={updateMutation.isPending}
              className="rounded-lg"
            >
              <Save className="mr-2 h-4 w-4" />
              {updateMutation.isPending ? t('common.loading') : t('common.save')}
            </Button>
          </div>
        )}
      </section>

      {/* Members */}
      <section className="space-y-4 rounded-lg border bg-card p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-base font-semibold">{t('workspace.members')}</h2>
            <Badge variant="outline" className="text-[11px]">
              {members.length}
            </Badge>
          </div>
          {canManage && (
            <Button
              onClick={() => setInviteOpen(true)}
              size="sm"
              className="rounded-lg"
            >
              <Plus className="mr-2 h-4 w-4" />
              {t('workspace.addMember')}
            </Button>
          )}
        </div>

        {membersQuery.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : members.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t('workspace.noMembers')}{' '}
            {canManage && t('workspace.noMembersHint')}
          </p>
        ) : (
          <ul className="divide-y">
            {members.map((m) => {
              const isMe = m.user_id === currentUser?.id
              return (
                <li key={m.id} className="py-3 flex items-center gap-3">
                  <Avatar className="h-9 w-9">
                    <AvatarFallback className="bg-primary/15 text-primary text-xs font-semibold">
                      {(m.display_name || m.email).slice(0, 2).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {m.display_name || m.email}
                      {isMe && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          ({t('workspace.you')})
                        </span>
                      )}
                    </p>
                    {m.display_name && (
                      <p className="text-xs text-muted-foreground truncate">{m.email}</p>
                    )}
                  </div>
                  {canManage && !isMe ? (
                    <select
                      value={m.role}
                      onChange={(e) =>
                        roleChangeMutation.mutate({
                          member: m,
                          role: e.target.value as WorkspaceRole,
                        })
                      }
                      className="h-9 w-32 rounded-lg border border-input bg-background px-2 text-sm"
                    >
                      {(['owner', 'editor', 'viewer'] as WorkspaceRole[]).map((r) => (
                        <option key={r} value={r}>
                          {labelForRole(r, t)}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <Badge variant="secondary" className="text-[11px]">
                      {labelForRole(m.role, t)}
                    </Badge>
                  )}
                  {canManage && !isMe && (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setRemoveTarget(m)}
                      title={t('workspace.remove')}
                      className="rounded-lg"
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {/* Invite dialog */}
      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('workspace.addMemberTitle')}</DialogTitle>
            <DialogDescription>{t('workspace.addMemberDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <div className="space-y-1.5">
              <Label htmlFor="invite-email" className="text-[13px]">
                {t('admin.users.email', 'Email')}
              </Label>
              <Input
                id="invite-email"
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                autoFocus
                className="h-10 rounded-lg"
                placeholder="user@example.com"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="invite-role" className="text-[13px]">
                {t('workspace.role')}
              </Label>
              <select
                id="invite-role"
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as WorkspaceRole)}
                className="w-full h-10 rounded-lg border border-input bg-background px-3 text-sm"
              >
                {(['owner', 'editor', 'viewer'] as WorkspaceRole[]).map((r) => (
                  <option key={r} value={r}>
                    {labelForRole(r, t)} — {hintForRole(r, t)}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="invite-password" className="text-[13px]">
                {t('workspace.passwordForNewUsers')}
              </Label>
              <Input
                id="invite-password"
                type="password"
                value={invitePassword}
                onChange={(e) => setInvitePassword(e.target.value)}
                className="h-10 rounded-lg"
                placeholder=""
              />
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                {t('workspace.passwordHint')}
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setInviteOpen(false)}
              className="rounded-lg"
            >
              {t('common.cancel')}
            </Button>
            <Button
              onClick={() => inviteMutation.mutate()}
              disabled={inviteMutation.isPending || !inviteEmail.trim()}
              className="rounded-lg"
            >
              {inviteMutation.isPending ? t('common.loading') : t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirm remove dialog */}
      <Dialog
        open={!!removeTarget}
        onOpenChange={(open) => !open && setRemoveTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('workspace.removeConfirmTitle')}</DialogTitle>
            <DialogDescription>
              {t('workspace.removeConfirmDescription', {
                email: removeTarget?.email,
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setRemoveTarget(null)}
              className="rounded-lg"
            >
              {t('common.cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={() => removeTarget && removeMutation.mutate(removeTarget)}
              disabled={removeMutation.isPending}
              className="rounded-lg"
            >
              {removeMutation.isPending ? t('common.loading') : t('workspace.remove')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
