import { useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Anchor, Button, Group, SegmentedControl, Stack, Switch, Text, TextInput, Textarea, NumberInput } from '@mantine/core'
import { IconAlertTriangle, IconArrowLeft, IconCalendarEvent, IconPlus, IconRefresh, IconSettings } from '@tabler/icons-react'
import { ConfirmModal, EmptyState, ErrorBanner, Field, LoadingSpinner, Modal, PageHead, Seg, formatDateTime, useT } from '@hubra/plugin-sdk'
import {
  QK,
  createMatch,
  deleteTeam,
  errorText,
  getOptions,
  listMatches,
  listTeams,
  syncTeam,
  updateMatch,
  type Match,
} from './api'
import { useAction } from './common'
import { MatchRow } from './parts'
import { TeamModal } from './TeamsScreen'

export function TeamScreen() {
  const { t } = useT()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const id = Number(useParams().id)
  const options = useQuery({ queryKey: QK.options, queryFn: getOptions })
  const teams = useQuery({ queryKey: QK.teams, queryFn: listTeams })
  const [past, setPast] = useState(false)
  const matches = useQuery({ queryKey: QK.matches(id, past), queryFn: () => listMatches(id, past) })
  const [adding, setAdding] = useState(false)
  const [settings, setSettings] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const { busy, run } = useAction()
  const team = teams.data?.find((tm) => tm.id === id)

  if (teams.error) return <ErrorBanner message={errorText(teams.error)} onRetry={() => teams.refetch()} />
  if (teams.isLoading) return <LoadingSpinner />
  if (!team) return <ErrorBanner message={t('teams.notFound')} />
  const coach = team.coach || !!options.data?.can.teams
  const inside = team.mine || team.coach

  return (
    <>
      <PageHead
        back={
          <Anchor component="button" size="sm" onClick={() => navigate('/app/teams')}>
            <Group gap={4}>
              <IconArrowLeft size={14} /> {t('teams.title')}
            </Group>
          </Anchor>
        }
        title={team.name}
        desc={t('teams.players', { count: team.players })}
        actions={
          coach ? (
            <Group gap="xs">
              {team.hasFeed && (
                <Button
                  variant="default"
                  leftSection={<IconRefresh size={16} />}
                  loading={busy}
                  onClick={async () => {
                    let msg = ''
                    const ok = await run(async () => {
                      const r = await syncTeam(team.id)
                      msg = t('teams.synced', { added: r.added, updated: r.updated, cancelled: r.cancelled })
                    })
                    qc.invalidateQueries({ queryKey: QK.all })
                    if (ok) await run(async () => undefined, msg)
                  }}
                >
                  {t('teams.sync')}
                </Button>
              )}
              <Button variant="default" leftSection={<IconSettings size={16} />} onClick={() => setSettings(true)}>
                {t('teams.settings')}
              </Button>
              <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>
                {t('teams.newMatch')}
              </Button>
            </Group>
          ) : undefined
        }
      />
      <Stack gap="md">
        {coach && team.feedError && (
          <Alert color="red" variant="light" icon={<IconAlertTriangle size={18} />}>
            {t('teams.feedError', { error: team.feedError })}
          </Alert>
        )}
        {coach && team.hasFeed && team.feedSyncedAt && !team.feedError && (
          <Text size="sm" c="dimmed">
            {t('teams.feedSynced', { when: formatDateTime(team.feedSyncedAt) })}
          </Text>
        )}
        <Seg
          options={[
            { value: 'next', label: t('teams.upcoming') },
            { value: 'past', label: t('teams.past') },
          ]}
          value={past ? 'past' : 'next'}
          onChange={(v) => setPast(v === 'past')}
        />
        {matches.error ? (
          <ErrorBanner message={errorText(matches.error)} onRetry={() => matches.refetch()} />
        ) : matches.isLoading ? (
          <LoadingSpinner />
        ) : !matches.data?.length ? (
          <EmptyState
            icon={<IconCalendarEvent size={28} />}
            title={past ? t('teams.noPast') : t('teams.noMatches')}
            description={coach && !past ? t('teams.noMatchesHint') : undefined}
          />
        ) : (
          <Stack gap="xs">
            {matches.data.map((m) => (
              <MatchRow key={m.id} match={m} inside={inside} onOpen={() => navigate(`/app/teams/matches/${m.id}`)} />
            ))}
          </Stack>
        )}
        {options.data?.can.teams && (
          <Group justify="flex-end">
            <Button variant="subtle" color="red" size="xs" onClick={() => setDeleting(true)}>
              {t('teams.deleteTeam')}
            </Button>
          </Group>
        )}
      </Stack>
      {adding && <MatchModal teamId={team.id} match={null} home={team.homeLocation} onClose={() => setAdding(false)} />}
      {settings && <TeamModal team={team} options={options.data} onClose={() => setSettings(false)} />}
      <ConfirmModal
        open={deleting}
        title={t('teams.deleteTeamTitle')}
        body={t('teams.deleteTeamBody')}
        confirmLabel={t('teams.delete')}
        onClose={() => setDeleting(false)}
        onConfirm={async () => {
          setDeleting(false)
          if (await run(() => deleteTeam(team.id))) {
            qc.invalidateQueries({ queryKey: QK.all })
            navigate('/app/teams')
          }
        }}
      />
    </>
  )
}

/** Add a match, or change one (with the result and calling it off). */
export function MatchModal({ teamId, match, home: homeLocation, onClose }: { teamId: number; match: Match | null; home?: string | null; onClose: () => void }) {
  const { t } = useT()
  const qc = useQueryClient()
  const { busy, run } = useAction()
  const [opponent, setOpponent] = useState(match?.opponent ?? '')
  const [day, setDay] = useState(match?.startsAt.slice(0, 10) ?? '')
  const [time, setTime] = useState(match?.startsAt.slice(11, 16) ?? '')
  const [meet, setMeet] = useState(match?.meetAt?.slice(11, 16) ?? '')
  const [home, setHome] = useState(match?.home === null || match?.home === undefined ? (match ? 'neutral' : 'home') : match.home ? 'home' : 'away')
  const [location, setLocation] = useState(match?.location ?? '')
  const [competition, setCompetition] = useState(match?.competition ?? '')
  const [notes, setNotes] = useState(match?.notes ?? '')
  const [cancelled, setCancelled] = useState(match?.cancelled ?? false)
  const [scoreUs, setScoreUs] = useState<number | string>(match?.scoreUs ?? '')
  const [scoreThem, setScoreThem] = useState<number | string>(match?.scoreThem ?? '')

  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    const body: Record<string, unknown> = {
      opponent,
      startsAt: `${day}T${time}`,
      meetAt: meet ? `${day}T${meet}` : null,
      home: home === 'neutral' ? null : home === 'home',
      location: location || null,
      competition: competition || null,
      notes: notes || null,
    }
    if (match) Object.assign(body, { cancelled, scoreUs: scoreUs === '' ? null : scoreUs, scoreThem: scoreThem === '' ? null : scoreThem })
    const ok = await run(() => (match ? updateMatch(match.id, body) : createMatch(teamId, body)), t('teams.saved'))
    if (ok) {
      qc.invalidateQueries({ queryKey: QK.all })
      onClose()
    }
  }

  return (
    <Modal
      open
      wide
      onClose={onClose}
      onSubmit={submit}
      title={match ? t('teams.editMatch') : t('teams.newMatch')}
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            {t('teams.cancel')}
          </Button>
          <Button type="submit" loading={busy} disabled={!opponent.trim() || !day || !time}>
            {t('teams.save')}
          </Button>
        </>
      }
    >
      <Field label={t('teams.opponent')}>
        <TextInput value={opponent} onChange={(e) => setOpponent(e.currentTarget.value)} data-autofocus />
      </Field>
      <Group grow align="flex-start">
        <Field label={t('teams.day')}>
          <TextInput type="date" value={day} onChange={(e) => setDay(e.currentTarget.value)} />
        </Field>
        <Field label={t('teams.kickoff')}>
          <TextInput type="time" value={time} onChange={(e) => setTime(e.currentTarget.value)} />
        </Field>
        <Field label={t('teams.meet')}>
          <TextInput type="time" value={meet} onChange={(e) => setMeet(e.currentTarget.value)} />
        </Field>
      </Group>
      <Field label={t('teams.where')}>
        <SegmentedControl
          fullWidth
          value={home}
          onChange={(v) => {
            setHome(v)
            if (v === 'home' && !location && homeLocation) setLocation(homeLocation)
          }}
          data={[
            { value: 'home', label: t('teams.home') },
            { value: 'away', label: t('teams.away') },
            { value: 'neutral', label: t('teams.neutral') },
          ]}
        />
      </Field>
      <Group grow align="flex-start">
        <Field label={t('teams.location')}>
          <TextInput value={location} onChange={(e) => setLocation(e.currentTarget.value)} placeholder={home === 'home' ? homeLocation ?? '' : ''} />
        </Field>
        <Field label={t('teams.competition')}>
          <TextInput value={competition} onChange={(e) => setCompetition(e.currentTarget.value)} placeholder={t('teams.competitionExample')} />
        </Field>
      </Group>
      <Field label={t('teams.notes')}>
        <Textarea value={notes} onChange={(e) => setNotes(e.currentTarget.value)} autosize minRows={2} />
      </Field>
      {match && (
        <>
          <Group grow align="flex-start">
            <Field label={t('teams.scoreUs')}>
              <NumberInput value={scoreUs} onChange={setScoreUs} min={0} max={999} />
            </Field>
            <Field label={t('teams.scoreThem')}>
              <NumberInput value={scoreThem} onChange={setScoreThem} min={0} max={999} />
            </Field>
          </Group>
          <Switch checked={cancelled} onChange={(e) => setCancelled(e.currentTarget.checked)} label={t('teams.callOff')} />
        </>
      )}
    </Modal>
  )
}
