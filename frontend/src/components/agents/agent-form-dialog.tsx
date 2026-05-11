import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Settings2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { agents } from '@/lib/api'
import type { Agent } from '@/lib/api'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  agent?: Agent | null
  providers: string[]
}

const NO_CONNECTION = '__none__'

export function AgentFormDialog({ open, onOpenChange, agent }: Props) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const isEdit = !!agent
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [connectionId, setConnectionId] = useState<string>(NO_CONNECTION)
  const [model, setModel] = useState('')
  const [temperature, setTemperature] = useState('0.4')
  const [autoContext, setAutoContext] = useState(true)
  const [isDefault, setIsDefault] = useState(false)

  const { data: connections } = useQuery({
    queryKey: ['agent-connections'],
    queryFn: () => agents.connections.list(),
    enabled: open,
  })

  useEffect(() => {
    if (agent) {
      setName(agent.name)
      setDescription(agent.description ?? '')
      setSystemPrompt(agent.system_prompt ?? '')
      setConnectionId(agent.connection_id ?? NO_CONNECTION)
      setModel(agent.model ?? '')
      setTemperature(String(agent.temperature ?? 0.4))
      setAutoContext(agent.auto_context ?? true)
      setIsDefault(agent.is_default ?? false)
    } else {
      setName('')
      setDescription('')
      setSystemPrompt('')
      setConnectionId(NO_CONNECTION)
      setModel('')
      setTemperature('0.4')
      setAutoContext(true)
      setIsDefault(false)
    }
  }, [agent, open])

  const selectedConnection = connections?.find((c) => c.id === connectionId)

  const saveMut = useMutation({
    mutationFn: (payload: Partial<Agent> & { name: string }) =>
      isEdit && agent ? agents.update(agent.id, payload) : agents.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents'] })
      onOpenChange(false)
      toast.success(isEdit ? t('agents.form.updated') : t('agents.form.created'))
    },
    onError: (err: unknown) => {
      const message = (err as { message?: string })?.message ?? t('agents.form.saveFailed')
      toast.error(message)
    },
  })

  const submit = () => {
    if (!name.trim()) {
      toast.error(t('agents.form.nameRequired'))
      return
    }
    saveMut.mutate({
      name: name.trim(),
      description: description.trim() || null,
      system_prompt: systemPrompt,
      connection_id: connectionId === NO_CONNECTION ? null : connectionId,
      model: model.trim() || null,
      temperature: Number(temperature) || 0.4,
      auto_context: autoContext,
      is_default: isDefault,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? t('agents.form.editTitle') : t('agents.form.createTitle')}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label htmlFor="agent-name">{t('agents.form.name')}</Label>
            <Input id="agent-name" value={name} onChange={(e) => setName(e.target.value)} placeholder={t('agents.form.namePlaceholder')} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="agent-desc">{t('agents.form.description')}</Label>
            <Input
              id="agent-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('agents.form.descriptionPlaceholder')}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="agent-prompt">{t('agents.form.systemPrompt')}</Label>
            <textarea
              id="agent-prompt"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={6}
              className="rounded-md border bg-background px-3 py-2 text-sm font-mono"
              placeholder={t('agents.form.systemPromptPlaceholder')}
            />
          </div>
          <div className="grid grid-cols-[1fr_1fr] gap-3">
            <div className="grid gap-2">
              <div className="flex items-center justify-between">
                <Label>{t('agents.form.connection')}</Label>
                <Link
                  to="/agents/connections"
                  className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
                  onClick={() => onOpenChange(false)}
                >
                  <Settings2 className="h-3 w-3" />
                  {t('agents.form.manageConnections')}
                </Link>
              </div>
              <Select value={connectionId} onValueChange={setConnectionId}>
                <SelectTrigger>
                  <SelectValue placeholder={t('agents.instanceDefault')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_CONNECTION}>{t('agents.instanceDefault')}</SelectItem>
                  {(connections ?? []).map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name} <span className="text-muted-foreground ml-1">({c.kind})</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="agent-model">{t('agents.form.model')}</Label>
              <Input
                id="agent-model"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={selectedConnection?.default_model || t('agents.form.modelPlaceholder')}
              />
              {!model && selectedConnection?.default_model && (
                <p className="text-xs text-muted-foreground">{t('agents.form.willUseConnectionDefault', { model: selectedConnection.default_model })}</p>
              )}
            </div>
          </div>
          <div className="grid gap-2 max-w-[160px]">
            <Label htmlFor="agent-temp">{t('agents.form.temperature')}</Label>
            <Input
              id="agent-temp"
              type="number"
              step="0.05"
              min="0"
              max="2"
              value={temperature}
              onChange={(e) => setTemperature(e.target.value)}
            />
          </div>
          <div className="rounded-md border p-3 flex items-start gap-3">
            <Switch checked={autoContext} onCheckedChange={(v) => setAutoContext(!!v)} />
            <div className="min-w-0 flex-1">
              <Label className="cursor-pointer" onClick={() => setAutoContext(!autoContext)}>
                {t('agents.form.autoContext')}
              </Label>
              <p className="text-xs text-muted-foreground mt-0.5">{t('agents.form.autoContextHint')}</p>
            </div>
          </div>
          <div className="rounded-md border p-3 flex items-start gap-3">
            <Switch checked={isDefault} onCheckedChange={(v) => setIsDefault(!!v)} />
            <div className="min-w-0 flex-1">
              <Label className="cursor-pointer" onClick={() => setIsDefault(!isDefault)}>
                {t('agents.form.isDefault', 'Default agent')}
              </Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                {t(
                  'agents.form.isDefaultHint',
                  'Used by the global slide-over chat (⌘J). Only one agent can be the default — turning this on clears it on others.',
                )}
              </p>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('agents.form.cancel')}
          </Button>
          <Button onClick={submit} disabled={saveMut.isPending}>
            {saveMut.isPending ? t('agents.form.saving') : isEdit ? t('agents.form.save') : t('agents.form.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
