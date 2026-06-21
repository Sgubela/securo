import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { connections } from '@/lib/api'
import { invalidateFinancialQueries } from '@/lib/invalidate-queries'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ExternalLink } from 'lucide-react'
import { toast } from 'sonner'

interface TokenConnectDialogProps {
  open: boolean
  onClose: () => void
  provider: string
}

const PROVIDER_BRIDGE_URLS: Record<string, string> = {
  simplefin: 'https://bridge.simplefin.org/simplefin/create',
}

export function TokenConnectDialog({ open, onClose, provider }: TokenConnectDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [token, setToken] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [environment, setEnvironment] = useState<'live' | 'demo'>('live')
  const [importHistory, setImportHistory] = useState(true)
  const [historyStart, setHistoryStart] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) {
      setToken('')
      setApiKey('')
      setApiSecret('')
      setEnvironment('live')
      setImportHistory(true)
      setHistoryStart('')
      setSubmitting(false)
    }
  }, [open])

  const bridgeUrl = PROVIDER_BRIDGE_URLS[provider]
  const i18nKey = `accounts.tokenConnect.${provider}`
  const isTrading212 = provider === 'trading212'
  const canSubmit = isTrading212 ? apiKey.trim() && apiSecret.trim() : token.trim()

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    try {
      const connection = await connections.handleCallback(
        isTrading212
          ? `${environment}:${apiKey.trim()}:${apiSecret.trim()}`
          : token.trim(),
        provider,
      )
      if (isTrading212) {
        await connections.updateSettings(connection.id, {
          trading212_history_import_enabled: importHistory,
          trading212_history_start: historyStart.trim() || null,
        })
      }
      invalidateFinancialQueries(queryClient)
      queryClient.invalidateQueries({ queryKey: ['connections'] })
      toast.success(t('accounts.connected'))
      onClose()
    } catch (err) {
      const detail =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? typeof err.response.data.detail === 'string'
            ? err.response.data.detail
            : err.response.data.detail.message
          : null
      toast.error(detail || t('accounts.connectError'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && !submitting && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t(`${i18nKey}.title`, t('accounts.tokenConnect.defaultTitle'))}</DialogTitle>
          <p className="text-sm text-muted-foreground">
            {t(`${i18nKey}.description`, t('accounts.tokenConnect.defaultDescription'))}
          </p>
        </DialogHeader>

        {bridgeUrl && (
          <Button asChild variant="outline" className="w-full justify-between">
            <a href={bridgeUrl} target="_blank" rel="noreferrer">
              <span>{t('accounts.tokenConnect.openBridge')}</span>
              <ExternalLink size={14} />
            </a>
          </Button>
        )}

        {isTrading212 ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
              {t('accounts.tokenConnect.trading212.readOnlyNotice')}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="trading212-environment">{t('accounts.tokenConnect.trading212.environment')}</Label>
              <select
                id="trading212-environment"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                value={environment}
                onChange={(e) => setEnvironment(e.target.value as 'live' | 'demo')}
                disabled={submitting}
              >
                <option value="live">{t('accounts.tokenConnect.trading212.live')}</option>
                <option value="demo">{t('accounts.tokenConnect.trading212.demo')}</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="trading212-api-key">{t('accounts.tokenConnect.trading212.apiKeyLabel')}</Label>
              <Input
                id="trading212-api-key"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                autoComplete="off"
                spellCheck={false}
                disabled={submitting}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="trading212-api-secret">{t('accounts.tokenConnect.trading212.apiSecretLabel')}</Label>
              <Input
                id="trading212-api-secret"
                type="password"
                value={apiSecret}
                onChange={(e) => setApiSecret(e.target.value)}
                autoComplete="off"
                spellCheck={false}
                disabled={submitting}
              />
              <p className="text-xs text-muted-foreground">
                {t('accounts.tokenConnect.trading212.scopesHelp')}
              </p>
            </div>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={importHistory}
                onChange={(e) => setImportHistory(e.target.checked)}
                disabled={submitting}
              />
              <span>
                <span className="font-medium">{t('accounts.tokenConnect.trading212.importHistory')}</span>
                <span className="block text-xs text-muted-foreground">
                  {t('accounts.tokenConnect.trading212.importHistoryHelp')}
                </span>
              </span>
            </label>
            <div className="space-y-1.5">
              <Label htmlFor="trading212-history-start">{t('accounts.tokenConnect.trading212.historyStart')}</Label>
              <Input
                id="trading212-history-start"
                type="date"
                value={historyStart}
                onChange={(e) => setHistoryStart(e.target.value)}
                disabled={submitting || !importHistory}
              />
            </div>
          </div>
        ) : (
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="securo-token-input">
              {t('accounts.tokenConnect.tokenLabel')}
            </label>
            <textarea
              id="securo-token-input"
              className="w-full min-h-[110px] rounded-md border border-input bg-background px-3 py-2 text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-0"
              placeholder={t('accounts.tokenConnect.tokenPlaceholder')}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              spellCheck={false}
              autoComplete="off"
              disabled={submitting}
            />
            <p className="text-xs text-muted-foreground">
              {t('accounts.tokenConnect.tokenHelp')}
            </p>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit || submitting}>
            {submitting
              ? t('accounts.tokenConnect.connecting')
              : t('accounts.tokenConnect.connect')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
