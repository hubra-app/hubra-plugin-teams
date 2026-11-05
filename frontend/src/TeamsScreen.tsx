import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge, Box, Button, Group, Paper, Select, SimpleGrid, Stack, Switch, Text, TextInput } from '@mantine/core'
import { IconPlus, IconShirtSport } from '@tabler/icons-react'
import { EmptyState, ErrorBanner, Field, LoadingSpinner, Modal, PageHead, useT } from '@hubra/plugin-sdk'
import { QK, errorText, getOptions, listTeams, saveTeam, type Options, type Team } from './api'
import { useAction } from './common'
import { AnswerButtons, Counts, HomeBadge, when } from './parts'

/** Every team, the caller's own first, each with its next match. */
export function TeamsScreen() {
  const { t } = useT()
  const navigate = useNavigate()
  const options = useQuery({ queryKey: QK.options, queryFn: getOptions })
  const teams = useQuery({ queryKey: QK.teams, queryFn: listTeams })
  const [adding, setAdding] = useState(false)
  const manage = !!options.data?.can.teams

  if (teams.error) return <ErrorBanner message={errorText(teams.error)} onRetry={() => teams.refetch()} />
  if (teams.isLoading || options.isLoading) return <LoadingSpinner />
  const list = teams.data ?? []
  const mine = list.filter((tm) => tm.mine || tm.coach)
  const others = list.filter((tm) => !(tm.mine || tm.coach))

  return (
    <>
      <PageHead
        title={t('teams.title')}
        desc={t('teams.desc')}
        actions={
          manage ? (
            <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>
              {t('teams.newTeam')}
            </Button>
          ) : undefined
        }
      />
      {!list.length ? (
        <EmptyState icon={<IconShirtSport size={28} />} title={t('teams.none')} description={manage ? t('teams.noneHint') : undefined} />
      ) : (
        <Stack gap="lg">
          {mine.length > 0 && <TeamGrid teams={mine} onOpen={(id) => navigate(`/app/teams/${id}`)} />}
          {others.length > 0 && (
            <div>
              {mine.length > 0 && (
                <Text fw={600} mb="xs">
                  {t('teams.otherTeams')}
                </Text>
              )}
              <TeamGrid teams={others} onOpen={(id) => navigate(`/app/teams/${id}`)} />
            </div>
          )}
        </Stack>
      )}
      {adding && (
        <TeamModal
          team={null}
          options={options.data}
          onClose={() => setAdding(false)}
          onDone={(tm) => navigate(`/app/teams/${tm.id}`)}
        />
      )}
    </>
  )
}

function TeamGrid({ teams, onOpen }: { teams: Team[]; onOpen: (id: number) => void }) {
  const { t, i18n } = useT()
  const locale = i18n.language?.startsWith('de') ? 'de-CH' : 'en-GB'
  return (
    <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
      {teams.map((tm) => (
        <Paper key={tm.id} withBorder radius="md" p="md" style={{ cursor: 'pointer' }} onClick={() => onOpen(tm.id)}>
          <Group justify="space-between" wrap="nowrap" mb="xs">
            <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
              <Box style={{ width: 10, height: 10, borderRadius: '50%', flexShrink: 0, background: tm.color || 'var(--mantine-color-violet-filled)' }} />
              <Text fw={700} truncate>
                {tm.name}
              </Text>
            </Group>
            <Group gap={6} wrap="nowrap">
              {tm.coach && (
                <Badge size="sm" variant="light" color="violet" style={{ textTransform: 'none' }}>
                  {t('teams.coachBadge')}
                </Badge>
              )}
              <Text size="xs" c="dimmed">
                {t('teams.players', { count: tm.players })}
              </Text>
            </Group>
          </Group>
          {tm.next ? (
            <Stack gap={6}>
              <Group gap={6} wrap="nowrap">
                <Text size="sm" c="dimmed" style={{ flexShrink: 0 }}>
                  {t('teams.next')}
                </Text>
                <Text size="sm" fw={600} truncate>
                  {tm.next.opponent}
                </Text>
                <HomeBadge home={tm.next.home} />
              </Group>
              <Text size="sm" c="dimmed">
                {when(tm.next, locale)}
                {tm.next.location ? ` · ${tm.next.location}` : ''}
              </Text>
              {(tm.mine || tm.coach) && (
                <Group gap="md" wrap="wrap">
                  {tm.mine && <AnswerButtons match={tm.next} />}
                  <Counts match={tm.next} />
                </Group>
              )}
            </Stack>
          ) : (
            <Text size="sm" c="dimmed">
              {t('teams.noNext')}
            </Text>
          )}
        </Paper>
      ))}
    </SimpleGrid>
  )
}

/** Set a team up, or change its feed and calendar settings. */
export function TeamModal({
  team,
  options,
  onClose,
  onDone,
}: {
  team: Team | null
  options: Options | undefined
  onClose: () => void
  onDone?: (t: Team) => void
}) {
  const { t } = useT()
  const qc = useQueryClient()
  const { busy, run } = useAction()
  const [groupId, setGroupId] = useState<string | null>(null)
  const [feedUrl, setFeedUrl] = useState(team?.feedUrl ?? '')
  const [feedName, setFeedName] = useState(team?.feedName ?? '')
  const [homeLocation, setHomeLocation] = useState(team?.homeLocation ?? '')
  const [inCalendar, setInCalendar] = useState(team?.inCalendar ?? true)
  const groups = (options?.groups ?? []).slice().sort((a, b) => Number(b.type === 'team') - Number(a.type === 'team'))

  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    let saved: Team | undefined
    const ok = await run(async () => {
      saved = await saveTeam(
        { ...(team ? {} : { groupId: Number(groupId) }), feedUrl: feedUrl || null, feedName: feedName || null, homeLocation: homeLocation || null, inCalendar },
        team?.id,
      )
    }, t('teams.saved'))
    if (ok && saved) {
      qc.invalidateQueries({ queryKey: QK.all })
      onDone?.(saved)
      onClose()
    }
  }

  return (
    <Modal
      open
      wide
      onClose={onClose}
      onSubmit={submit}
      title={team ? t('teams.settings') : t('teams.newTeam')}
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            {t('teams.cancel')}
          </Button>
          <Button type="submit" loading={busy} disabled={!team && !groupId}>
            {t('teams.save')}
          </Button>
        </>
      }
    >
      {!team && (
        <Field label={t('teams.group')} hint={t('teams.groupHint')}>
          <Select
            aria-label={t('teams.group')}
            data={groups.map((g) => ({ value: String(g.id), label: g.name }))}
            value={groupId}
            onChange={setGroupId}
            searchable
            nothingFoundMessage={t('teams.noGroups')}
          />
        </Field>
      )}
      <Field label={t('teams.feedUrl')} hint={t('teams.feedUrlHint')}>
        <TextInput value={feedUrl} onChange={(e) => setFeedUrl(e.currentTarget.value)} placeholder="webcal://…" />
      </Field>
      <Group grow align="flex-start">
        <Field label={t('teams.feedName')} hint={t('teams.feedNameHint')}>
          <TextInput value={feedName} onChange={(e) => setFeedName(e.currentTarget.value)} placeholder={t('teams.feedNameExample')} />
        </Field>
        <Field label={t('teams.homeLocation')}>
          <TextInput value={homeLocation} onChange={(e) => setHomeLocation(e.currentTarget.value)} />
        </Field>
      </Group>
      <Switch checked={inCalendar} onChange={(e) => setInCalendar(e.currentTarget.checked)} label={t('teams.inCalendar')} />
    </Modal>
  )
}
